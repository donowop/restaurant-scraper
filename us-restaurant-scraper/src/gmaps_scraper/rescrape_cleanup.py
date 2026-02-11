"""Targeted re-scrape for restaurants with incomplete hours or missing price levels.

Loads Google cookies from a JSON file to authenticate with Google Maps,
which improves the success rate for extracting hours of operation and
price level data that is hidden from unauthenticated bot requests.

Usage:
    python -m gmaps_scraper.rescrape_cleanup --cookies cookies.json

Cookie file should be exported from a logged-in Google Chrome session.
See SETUP_GUIDE.md for instructions on exporting cookies.
"""

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from botasaurus.browser import browser, Driver
from botasaurus import bt

from gmaps_scraper.config import Config
from gmaps_scraper.extractors.details import (
    _normalize_text,
    _parse_time_to_24h,
    _handle_cookie_consent,
    _extract_price_level,
)


def _load_cookies(cookie_path: str) -> list[dict]:
    """Load cookies from a JSON file exported from browser.

    Formats cookies for Chrome DevTools Protocol (Storage.setCookies).
    Cookies with __Secure- prefix require secure=True.
    """
    with open(cookie_path) as f:
        raw = json.load(f)

    cookies = []
    for c in raw:
        name = c.get("name", "")
        domain = c.get("domain", ".google.com")

        # __Secure- prefixed cookies must have secure=True per CDP spec
        secure = c.get("secure", name.startswith("__Secure-"))

        cookie = {
            "name": name,
            "value": c.get("value", ""),
            "domain": domain,
            "path": c.get("path", "/"),
            "secure": secure,
        }

        # Only include optional fields if explicitly provided
        if c.get("httpOnly") is not None:
            cookie["httpOnly"] = c["httpOnly"]

        # Map EditThisCookie sameSite values to CDP format
        same_site_map = {
            "no_restriction": "None",
            "unspecified": "Lax",
            "lax": "Lax",
            "strict": "Strict",
            "Strict": "Strict",
            "Lax": "Lax",
            "None": "None",
        }
        raw_same_site = c.get("sameSite", "")
        if raw_same_site in same_site_map:
            cookie["sameSite"] = same_site_map[raw_same_site]
        elif secure:
            cookie["sameSite"] = "None"

        if c.get("expirationDate"):
            cookie["expires"] = c["expirationDate"]

        cookies.append(cookie)

    return cookies


def _identify_rescrape_targets(restaurants: list[dict]) -> list[dict]:
    """Identify restaurants that need re-scraping for hours or price."""
    targets = []
    for r in restaurants:
        needs_hours = False
        needs_price = False

        hours = r.get("hours_of_operation")
        if hours is None:
            needs_hours = True
        elif isinstance(hours, dict):
            if len(hours) < 7:
                needs_hours = True
            else:
                for day_data in hours.values():
                    if isinstance(day_data, dict) and day_data.get("close") == "unknown":
                        needs_hours = True
                        break

        if r.get("price_level") is None:
            needs_price = True

        if needs_hours or needs_price:
            targets.append({
                "restaurant": r,
                "needs_hours": needs_hours,
                "needs_price": needs_price,
            })

    return targets


def _extract_hours_authenticated(driver: Driver) -> Optional[dict[str, dict[str, str]]]:
    """Extract hours using the expanded table approach, with authenticated session."""
    days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    hours_dict: dict[str, dict[str, str]] = {}

    try:
        hours_selector = '[data-item-id="oh"]'

        if driver.is_element_present(hours_selector, wait=3):
            try:
                driver.run_js(
                    f"document.querySelector('{hours_selector}').scrollIntoView({{block: 'center'}})"
                )
                driver.sleep(1.5)
            except Exception:
                pass

            # Click the hours element directly to expand weekly view.
            # Google Maps uses two UI patterns:
            #   1. A separate arrow with aria-label="Show open hours for the week"
            #   2. The hours element itself is clickable ("Open · Closes X PM · See more hours")
            # Clicking [data-item-id="oh"] covers both patterns.
            try:
                driver.run_js(f"document.querySelector('{hours_selector}').click()")
                driver.sleep(4)
            except Exception:
                pass
        else:
            # Hours element not found - scroll down and try again
            try:
                driver.run_js(
                    "document.querySelector('[role=\"main\"]')?.scrollBy(0, 600)"
                )
                driver.sleep(1)
            except Exception:
                pass

            if driver.is_element_present(hours_selector, wait=3):
                try:
                    driver.run_js(f"document.querySelector('{hours_selector}').click()")
                    driver.sleep(4)
                except Exception:
                    pass

        html = driver.page_html

        # Primary: extract from the hours table rows
        table_pattern = (
            r'<tr[^>]*class="[^"]*y0skZc[^"]*"[^>]*>.*?<div>(\w+)</div>'
            r'.*?aria-label="([^"]*)".*?</tr>'
        )
        table_matches = re.findall(table_pattern, html, re.DOTALL | re.IGNORECASE)

        if table_matches:
            for day_name, time_text in table_matches:
                day_lower = day_name.lower()
                if day_lower in days:
                    time_text = _normalize_text(time_text)
                    time_text = re.sub(
                        r",?\s*Copy open hours.*$", "", time_text, flags=re.IGNORECASE
                    )

                    if "closed" in time_text.lower():
                        hours_dict[day_lower] = {"open": "closed", "close": "closed"}
                    elif "open 24 hours" in time_text.lower():
                        hours_dict[day_lower] = {"open": "00:00", "close": "23:59"}
                    else:
                        time_match = re.search(
                            r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*(?:to|–|-)\s*"
                            r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)",
                            time_text,
                            re.IGNORECASE,
                        )
                        if time_match:
                            open_time = _parse_time_to_24h(time_match.group(1))
                            close_time = _parse_time_to_24h(time_match.group(2))
                            hours_dict[day_lower] = {"open": open_time, "close": close_time}

        # Secondary: try the aria-label on individual day rows
        if len(hours_dict) < 7:
            day_patterns = [
                (day, rf'aria-label="[^"]*{day.capitalize()}[^"]*?'
                      rf'(\d{{1,2}}(?::\d{{2}})?\s*(?:AM|PM)?)\s*(?:to|–|-)\s*'
                      rf'(\d{{1,2}}(?::\d{{2}})?\s*(?:AM|PM)?)')
                for day in days
            ]
            for day, pattern in day_patterns:
                if day not in hours_dict:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        hours_dict[day] = {
                            "open": _parse_time_to_24h(match.group(1)),
                            "close": _parse_time_to_24h(match.group(2)),
                        }

        return hours_dict if hours_dict else None

    except Exception:
        return None


_cookies_loaded_for_driver: set[int] = set()


def _ensure_cookies_loaded(driver: Driver, cookies: list[dict]) -> None:
    """Load cookies once per driver instance. Navigates to google.com to set domain."""
    driver_id = id(driver)
    if driver_id in _cookies_loaded_for_driver:
        return

    driver.get("https://www.google.com")
    driver.sleep(1)

    # Set cookies individually, skipping any that fail
    for cookie in cookies:
        try:
            driver.add_cookies([cookie])
        except Exception:
            pass

    _cookies_loaded_for_driver.add(driver_id)
    driver.sleep(0.5)


@browser(
    block_images=True,
    cache=False,
    max_retry=2,
    retry_wait=5,
    headless=Config.HEADLESS,
    close_on_crash=True,
    reuse_driver=True,
    proxy=Config.PROXY_LIST[0] if Config.PROXY_LIST else None,
)
def _rescrape_single(driver: Driver, data: dict) -> Optional[dict]:
    """Re-scrape a single restaurant for hours and/or price with cookies loaded."""
    url = data["url"]
    cookies = data["cookies"]
    needs_hours = data["needs_hours"]
    needs_price = data["needs_price"]

    try:
        # Navigate to google.com, clear stale cookies, then load auth cookies.
        driver.get("https://www.google.com")
        driver.sleep(1)

        try:
            driver.delete_cookies()
        except Exception:
            pass

        for c in cookies:
            try:
                driver.add_cookies([c])
            except Exception:
                pass
        driver.sleep(0.5)

        driver.get(url)
        # Randomized delay to avoid bot detection patterns
        driver.sleep(4 + random.random() * 3)

        _handle_cookie_consent(driver)

        # Extract place name from URL for logging
        place_name = re.search(r"/place/([^/]+)/", url)
        place_label = place_name.group(1).replace("+", " ")[:40] if place_name else url[:50]
        print(f"  Scraping: {place_label}", flush=True)

        result = {"url": url}

        if needs_hours:
            hours = _extract_hours_authenticated(driver)
            result["hours_of_operation"] = hours
            if hours:
                result["hours_ok"] = len(hours) >= 7
                print(f"    -> Hours: {len(hours)} days extracted", flush=True)
            else:
                result["hours_ok"] = False
                print(f"    -> Hours: FAILED (no hours on listing)", flush=True)

        if needs_price:
            price = _extract_price_level(driver)
            result["price_level"] = price
            if price:
                print(f"    -> Price: {price}", flush=True)

        return result

    except Exception as e:
        print(f"  Error re-scraping {url[:60]}: {e}")
        return None


@browser(
    block_images=True,
    cache=False,
    max_retry=2,
    retry_wait=5,
    headless=Config.HEADLESS,
    close_on_crash=True,
    reuse_driver=True,
    parallel=1,
    proxy=Config.PROXY_LIST[0] if Config.PROXY_LIST else None,
)
def _rescrape_parallel(driver: Driver, data: dict) -> Optional[dict]:
    """Sequential re-scrape -- parallel>1 fails due to browser resource contention."""
    return _rescrape_single.__wrapped__(driver, data)


def _merge_results(restaurants: list[dict], rescrape_results: list[dict]) -> int:
    """Merge re-scraped data back into the main dataset. Returns count of updates."""
    url_to_result = {}
    for r in rescrape_results:
        if r and r.get("url"):
            url_to_result[r["url"]] = r

    updates = 0
    for restaurant in restaurants:
        url = restaurant.get("google_maps_url")
        if url not in url_to_result:
            continue

        result = url_to_result[url]
        changed = False

        if "hours_of_operation" in result and result.get("hours_ok"):
            restaurant["hours_of_operation"] = result["hours_of_operation"]
            changed = True

        if "price_level" in result and result["price_level"] is not None:
            restaurant["price_level"] = result["price_level"]
            changed = True

        if changed:
            restaurant["scraped_at"] = datetime.now().isoformat()
            updates += 1

    return updates


def run(
    input_path: str,
    cookie_path: str,
    output_path: str | None = None,
    batch_size: int = 50,
    dry_run: bool = False,
) -> None:
    """Run targeted re-scrape for restaurants with incomplete data."""
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    with open(input_file) as f:
        restaurants = json.load(f)

    targets = _identify_rescrape_targets(restaurants)

    hours_targets = [t for t in targets if t["needs_hours"]]
    price_targets = [t for t in targets if t["needs_price"]]

    print(f"\nRe-scrape targets:")
    print(f"  Need hours:  {len(hours_targets)}")
    print(f"  Need price:  {len(price_targets)}")
    print(f"  Total unique: {len(targets)}")

    if dry_run:
        print("\nDry run -- no scraping performed.")
        return

    cookie_file = Path(cookie_path)
    if not cookie_file.exists():
        print(f"Error: {cookie_path} not found")
        sys.exit(1)

    cookies = _load_cookies(cookie_path)
    print(f"Loaded {len(cookies)} cookies from {cookie_path}")

    # Build scrape tasks
    tasks = []
    for t in targets:
        url = t["restaurant"].get("google_maps_url")
        if url:
            tasks.append({
                "url": url,
                "cookies": cookies,
                "needs_hours": t["needs_hours"],
                "needs_price": t["needs_price"],
            })

    print(f"\nStarting re-scrape of {len(tasks)} restaurants...")

    # Load checkpoint if resuming
    checkpoint_path = Path("output/_rescrape_checkpoint.json")
    all_results = []
    start_idx = 0
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)
        all_results = checkpoint.get("results", [])
        start_idx = checkpoint.get("next_idx", 0)
        done_urls = {r["url"] for r in all_results if r}
        print(f"  Resuming from checkpoint: {len(all_results)} results, starting at index {start_idx}")

    total_hours_fixed = 0
    total_prices_found = 0

    for i in range(start_idx, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(tasks) + batch_size - 1) // batch_size

        print(f"\n--- Batch {batch_num}/{total_batches} ({len(batch)} places) ---", flush=True)

        results = _rescrape_parallel(batch)
        valid = [r for r in results if r is not None]
        all_results.extend(valid)

        hours_ok = sum(1 for r in valid if r.get("hours_ok"))
        price_ok = sum(1 for r in valid if r.get("price_level") is not None)
        total_hours_fixed += hours_ok
        total_prices_found += price_ok
        print(f"  Batch results: {len(valid)} scraped, {hours_ok} hours, {price_ok} prices")
        print(f"  Running total: {total_hours_fixed} hours fixed, {total_prices_found} prices found", flush=True)

        # Save checkpoint after each batch
        with open(checkpoint_path, "w") as f:
            json.dump({"results": all_results, "next_idx": i + batch_size}, f)

        if i + batch_size < len(tasks):
            print(f"  Waiting {Config.BATCH_DELAY}s...")
            time.sleep(Config.BATCH_DELAY)

    # Merge results
    updates = _merge_results(restaurants, all_results)

    if output_path is None:
        output_path = input_path

    with open(output_path, "w") as f:
        json.dump(restaurants, f, indent=2)

    # Also regenerate CSV
    csv_path = output_path.replace(".json", ".csv")
    bt.write_csv(restaurants, csv_path)

    # Clean up checkpoint
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    print(f"\nRe-scrape complete!")
    print(f"  Restaurants updated: {updates}")
    print(f"  Total hours fixed: {total_hours_fixed}")
    print(f"  Total prices found: {total_prices_found}")
    print(f"  Saved to: {output_path}")
    print(f"  CSV: {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Re-scrape restaurants with incomplete hours or price data"
    )
    parser.add_argument(
        "--input",
        default="output/all_restaurants.json",
        help="Path to restaurant JSON file (default: output/all_restaurants.json)",
    )
    parser.add_argument(
        "--cookies",
        default=None,
        help="Path to exported Google cookies JSON file (required unless --dry-run)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: overwrite input file)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for parallel scraping (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only identify targets, don't scrape",
    )

    args = parser.parse_args()

    if not args.dry_run and not args.cookies:
        parser.error("--cookies is required unless --dry-run is specified")

    run(args.input, args.cookies, args.output, args.batch_size, args.dry_run)


if __name__ == "__main__":
    main()
