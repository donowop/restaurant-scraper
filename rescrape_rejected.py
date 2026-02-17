#!/usr/bin/env python3
"""
Re-scrape places that were rejected/failed during the main detail phase.

Most of the ~48K rejected place_ids were never properly visited (empty driver
errors from cache=True/reuse_driver=True). This script re-visits them with
working settings, applies the 3+ star filter, and saves restaurants + food trucks.

Output:
  - output/rescrape_restaurants.json  (all 3+ star results)
  - output/food_trucks.json           (food trucks only, subset)

Usage:
    ./auto_rescrape.sh              # uses venv python
    ./auto_rescrape.sh --dry-run    # show counts only
"""

import argparse
import json
import os
import re
import time
from datetime import datetime

SCRAPER_ROOT = os.path.join(os.path.dirname(__file__), "us-restaurant-scraper")
CHECKPOINT_DIR = os.path.join(SCRAPER_ROOT, "checkpoints")
OUTPUT_DIR = os.path.join(SCRAPER_ROOT, "output")

SEEN_PLACES_FILE = os.path.join(CHECKPOINT_DIR, "seen_places.json")
PENDING_LINKS_FILE = os.path.join(CHECKPOINT_DIR, "pending_links.json")
SAVED_FILE = os.path.join(OUTPUT_DIR, "all_restaurants.json")

RESCRAPE_OUTPUT = os.path.join(OUTPUT_DIR, "rescrape_restaurants.json")
FOOD_TRUCKS_OUTPUT = os.path.join(OUTPUT_DIR, "food_trucks.json")
RESCRAPE_CHECKPOINT = os.path.join(CHECKPOINT_DIR, "rescrape_done.json")

URL_TEMPLATE = "https://www.google.com/maps/place/data=!4m2!3m1!1s{}"

MIN_RATING = 3.0


def _extract_place_id_from_url(url):
    m = re.search(r"!1s(0x[a-f0-9]+:0x[a-f0-9]+)", url)
    return m.group(1) if m else None


def recover_rejected_place_ids():
    """Find place_ids that were seen but not saved or pending."""
    with open(SEEN_PLACES_FILE) as f:
        seen = json.load(f)
    seen_ids = set(seen.get("place_ids", []))

    saved_ids = set()
    if os.path.exists(SAVED_FILE):
        with open(SAVED_FILE) as f:
            for r in json.load(f):
                if r.get("place_id"):
                    saved_ids.add(r["place_id"])

    pending_ids = set()
    if os.path.exists(PENDING_LINKS_FILE):
        with open(PENDING_LINKS_FILE) as f:
            for url in json.load(f):
                pid = _extract_place_id_from_url(url)
                if pid:
                    pending_ids.add(pid)

    rescrape_ids = set()
    if os.path.exists(RESCRAPE_CHECKPOINT):
        with open(RESCRAPE_CHECKPOINT) as f:
            rescrape_ids = set(json.load(f))

    rejected = seen_ids - saved_ids - pending_ids - rescrape_ids
    print(f"Seen: {len(seen_ids):,}")
    print(f"Saved: {len(saved_ids):,}")
    print(f"Pending: {len(pending_ids):,}")
    print(f"Already rescrape'd: {len(rescrape_ids):,}")
    print(f"To visit: {len(rejected):,}")

    return rejected


def rescrape_places(place_ids):
    """Re-scrape places with 3+ star filter. Saves all restaurants + food trucks."""
    from gmaps_scraper.config import Config
    from gmaps_scraper.extractors.details import (
        _extract_place_id,
        _normalize_text,
        _parse_rating,
        _extract_review_count,
        _extract_cuisine_type,
        _is_non_restaurant,
        _extract_website,
        _extract_phone,
        _extract_address,
        _extract_coordinates,
        _extract_hours,
        _extract_price_level,
        _extract_primary_photo,
        _parse_address_components,
        _handle_cookie_consent,
    )
    from botasaurus.browser import browser, Driver

    urls = [URL_TEMPLATE.format(pid) for pid in place_ids]
    print(f"\nTotal URLs to visit: {len(urls):,}")

    # Load existing results
    all_results = []
    if os.path.exists(RESCRAPE_OUTPUT):
        try:
            with open(RESCRAPE_OUTPUT) as f:
                all_results = json.load(f)
            print(f"Loaded {len(all_results):,} existing rescrape results")
        except Exception:
            pass

    done_ids = set()
    if os.path.exists(RESCRAPE_CHECKPOINT):
        with open(RESCRAPE_CHECKPOINT) as f:
            done_ids = set(json.load(f))

    urls = [u for u in urls if _extract_place_id_from_url(u) not in done_ids]
    print(f"Remaining after checkpoint: {len(urls):,}\n")

    if not urls:
        print("Nothing to rescrape!")
        return all_results

    batch_size = Config.DETAILS_BATCH_SIZE
    batch_num = 0
    stats = {"saved": 0, "low_rating": 0, "no_name": 0, "non_restaurant": 0, "errors": 0, "food_trucks": 0}
    consecutive_bad_batches = 0
    MAX_CONSECUTIVE_BAD_BATCHES = 3
    ERROR_RATE_THRESHOLD = 0.8  # halt if >80% errors

    @browser(
        block_images=False,
        cache=False,
        max_retry=3,
        retry_wait=5,
        headless=True,
        close_on_crash=True,
        parallel=Config.MAX_PARALLEL_BROWSERS or 4,
        reuse_driver=False,
        proxy=Config.PROXY_LIST[0] if Config.PROXY_LIST else None,
    )
    def _scrape_place(driver: Driver, place_url: str):
        """Scrape place details with 3+ star filter."""
        if not place_url:
            return None
        try:
            driver.get(place_url)
            driver.sleep(4)
            _handle_cookie_consent(driver)

            if "consent.google.com" in driver.current_url:
                driver.get(place_url)
                driver.sleep(4)

            place_id = _extract_place_id(place_url)

            name = None
            try:
                name = driver.get_text("h1")
                if name:
                    name = _normalize_text(name)
            except Exception:
                pass
            if not name:
                return {"_status": "no_name"}

            # Rating filter (same as main scraper)
            rating_text = None
            try:
                rating_text = driver.get_text("div.F7nice > span")
            except Exception:
                pass
            rating = _parse_rating(rating_text)

            if rating is None or rating < MIN_RATING:
                return {"_status": "low_rating"}

            # Full extraction
            review_count = _extract_review_count(driver)
            cuisine_type = _extract_cuisine_type(driver)

            # Filter non-restaurant entries (postal codes, neighborhoods, etc.)
            if _is_non_restaurant(cuisine_type):
                return {"_status": "non_restaurant"}

            website = _extract_website(driver)
            phone = _extract_phone(driver)
            address = _extract_address(driver)
            lat, lng = _extract_coordinates(driver.current_url)
            hours = _extract_hours(driver)
            price_level = _extract_price_level(driver)
            photo_url = _extract_primary_photo(driver)
            addr_components = _parse_address_components(address)

            is_food_truck = bool(cuisine_type and "food truck" in cuisine_type.lower())

            print(f"  {'FOOD TRUCK' if is_food_truck else 'Extracted'}: {name} ({rating} stars)")

            return {
                "place_id": place_id,
                "name": name,
                "business_type": "food_truck" if is_food_truck else "restaurant",
                "cuisine_type": cuisine_type,
                "address": address,
                "city": addr_components["city"],
                "state": addr_components["state"],
                "zip_code": addr_components["zip_code"],
                "latitude": lat,
                "longitude": lng,
                "phone": phone,
                "website": website,
                "rating": rating,
                "review_count": review_count,
                "price_level": price_level,
                "hours_of_operation": hours,
                "primary_photo_url": photo_url,
                "google_maps_url": place_url,
                "scraped_at": datetime.now().isoformat(),
            }
        except Exception as e:
            print(f"  Error: {e}")
            return {"_status": "error", "_msg": str(e)}

    for i in range(0, len(urls), batch_size):
        batch = urls[i : i + batch_size]
        batch_num += 1
        print(f"\n--- Batch {batch_num} ({len(batch)} places, {i:,}/{len(urls):,}) ---")

        try:
            results = _scrape_place(batch)

            for r in results:
                if r is None:
                    stats["errors"] += 1
                elif r.get("_status") == "no_name":
                    stats["no_name"] += 1
                elif r.get("_status") == "low_rating":
                    stats["low_rating"] += 1
                elif r.get("_status") == "non_restaurant":
                    stats["non_restaurant"] += 1
                elif r.get("_status") == "error":
                    stats["errors"] += 1
                else:
                    all_results.append(r)
                    stats["saved"] += 1
                    if r.get("business_type") == "food_truck":
                        stats["food_trucks"] += 1

            # Error rate check for this batch
            batch_errors = sum(1 for r in results if r is None or (isinstance(r, dict) and r.get("_status") == "error"))
            batch_error_rate = batch_errors / len(batch) if batch else 0

            print(
                f"  saved={stats['saved']:,} | low_rating={stats['low_rating']:,} | "
                f"no_name={stats['no_name']:,} | errors={stats['errors']:,} | "
                f"food_trucks={stats['food_trucks']} | "
                f"batch_error_rate={batch_error_rate:.0%}"
            )

            if batch_error_rate > ERROR_RATE_THRESHOLD:
                consecutive_bad_batches += 1
                print(f"  WARNING: High error rate! ({consecutive_bad_batches}/{MAX_CONSECUTIVE_BAD_BATCHES} consecutive)")
                if consecutive_bad_batches >= MAX_CONSECUTIVE_BAD_BATCHES:
                    print(f"\n  HALTING: {MAX_CONSECUTIVE_BAD_BATCHES} consecutive batches with >{ERROR_RATE_THRESHOLD:.0%} error rate.")
                    print("  This likely means browser connections are failing. Check Chrome/driver status.")
                    break
            else:
                consecutive_bad_batches = 0

            # Checkpoint
            for url in batch:
                pid = _extract_place_id_from_url(url)
                if pid:
                    done_ids.add(pid)

            with open(RESCRAPE_CHECKPOINT, "w") as f:
                json.dump(list(done_ids), f)

        except Exception as e:
            print(f"  Batch error: {e}")

        time.sleep(Config.BATCH_DELAY)

    # Final save
    with open(RESCRAPE_OUTPUT, "w") as f:
        json.dump(all_results, f)

    food_trucks = [r for r in all_results if r.get("business_type") == "food_truck"]
    with open(FOOD_TRUCKS_OUTPUT, "w") as f:
        json.dump(food_trucks, f)

    # Merge rescrape results into all_restaurants.json (single source of truth)
    print(f"\nMerging into {SAVED_FILE}...")
    existing = []
    if os.path.exists(SAVED_FILE):
        with open(SAVED_FILE) as f:
            existing = json.load(f)

    seen_pids = {r.get("place_id") for r in existing if r.get("place_id")}
    new_count = 0
    for r in all_results:
        pid = r.get("place_id")
        if pid and pid not in seen_pids:
            existing.append(r)
            seen_pids.add(pid)
            new_count += 1

    with open(SAVED_FILE, "w") as f:
        json.dump(existing, f)

    # Write food trucks as a convenience subset
    food_trucks = [r for r in existing if r.get("business_type") == "food_truck"]
    with open(FOOD_TRUCKS_OUTPUT, "w") as f:
        json.dump(food_trucks, f)

    # Clean up separate rescrape file — data is now in all_restaurants.json
    if os.path.exists(RESCRAPE_OUTPUT):
        os.remove(RESCRAPE_OUTPUT)

    print(f"\n{'='*60}")
    print("RESCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Places visited:      {len(done_ids):,}")
    print(f"New restaurants:      {new_count:,}")
    print(f"Food trucks (total):  {len(food_trucks)}")
    print(f"all_restaurants.json: {len(existing):,} total")
    print(f"Low rating:           {stats['low_rating']:,}")
    print(f"No name:              {stats['no_name']:,}")
    print(f"Errors:               {stats['errors']:,}")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Re-scrape rejected/failed places")
    parser.add_argument("--dry-run", action="store_true", help="Show counts only")
    args = parser.parse_args()

    print("=" * 60)
    print("RESCRAPE REJECTED/FAILED PLACES")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Rating filter: {MIN_RATING}+ stars\n")

    print("--- Recovering place_ids ---")
    rejected = recover_rejected_place_ids()

    if args.dry_run:
        print("\nDry run — no scraping performed.")
        return

    rescrape_places(list(rejected))


if __name__ == "__main__":
    main()
