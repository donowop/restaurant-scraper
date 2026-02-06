"""Place detail scraper for Google Maps - extracts detailed restaurant information."""

import re
import urllib.parse
from datetime import datetime
from typing import Optional

from botasaurus.browser import browser, Driver

from gmaps_scraper.config import Config


def _get_element_or_none(driver: Driver, selector: str):
    """Helper function to get an element or return None if not found."""
    try:
        if driver.is_element_present(selector, wait=2):
            return driver.select(selector, wait=2)
    except Exception:
        pass
    return None


def _normalize_text(text: str) -> str:
    """Normalize unicode characters in text."""
    if not text:
        return text
    text = text.replace("\u202f", " ")  # narrow no-break space
    text = text.replace("\u00a0", " ")  # non-breaking space
    text = text.replace("\u2019", "'")  # right single quote
    text = text.replace("\u2018", "'")  # left single quote
    text = text.replace("\u201c", '"')  # left double quote
    text = text.replace("\u201d", '"')  # right double quote
    text = text.replace("\u2013", "-")  # en dash
    text = text.replace("\u2014", "-")  # em dash
    return text


def _parse_time_to_24h(time_str: str) -> str:
    """Convert time string like '10 AM' or '10:30 PM' to 24-hour format."""
    if not time_str:
        return ""

    time_str = _normalize_text(time_str).strip().upper()
    match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", time_str)
    if not match:
        return time_str

    hours = int(match.group(1))
    minutes = match.group(2) or "00"
    period = match.group(3)

    if period == "PM" and hours != 12:
        hours += 12
    elif period == "AM" and hours == 12:
        hours = 0

    return f"{hours:02d}:{minutes}"


def _extract_place_id(url: str) -> Optional[str]:
    """Extract place_id from Google Maps URL."""
    match = re.search(r"!1s(0x[a-f0-9]+:0x[a-f0-9]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"data=.*?(0x[a-f0-9]+:0x[a-f0-9]+)", url)
    if match:
        return match.group(1)

    match = re.search(r"/maps/place/([^/]+)", url)
    if match:
        return urllib.parse.unquote(match.group(1))

    return None


def _extract_coordinates(url: str) -> tuple[Optional[float], Optional[float]]:
    """Extract latitude and longitude from Google Maps URL."""
    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def _parse_rating(rating_text: str) -> Optional[float]:
    """Parse rating from text like '4.5' or '4,5'."""
    if not rating_text:
        return None
    try:
        cleaned = rating_text.replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def _parse_review_count(reviews_text: str) -> Optional[int]:
    """Parse review count from text like '(1,234 reviews)'."""
    if not reviews_text:
        return None
    try:
        digits = "".join(filter(str.isdigit, reviews_text))
        return int(digits) if digits else None
    except (ValueError, AttributeError):
        return None


def _handle_cookie_consent(driver: Driver) -> None:
    """Accept cookies if consent form appears."""
    if driver.is_in_page("consent.google.com"):
        try:
            agree_selector = "form:nth-child(2) > div > div > button"
            driver.click(agree_selector)
            driver.sleep(1)
        except Exception:
            pass


def _extract_cuisine_type(driver: Driver) -> Optional[str]:
    """Extract cuisine/category from the place page."""
    selectors = [
        "button[jsaction*='category']",
        "button[jsaction*='pane.rating.category']",
        ".DkEaL",
        "[data-item-id='category']",
    ]

    for selector in selectors:
        try:
            text = driver.get_text(selector)
            if text:
                return text.strip()
        except Exception:
            continue

    return None


def _extract_phone(driver: Driver) -> Optional[str]:
    """Extract phone number from data-item-id attribute."""
    try:
        phone_selector = '[data-item-id^="phone"]'
        phone_element = _get_element_or_none(driver, phone_selector)
        if phone_element:
            data_id = phone_element.get_attribute("data-item-id")
            if data_id:
                return data_id.replace("phone:tel:", "")
    except Exception:
        pass
    return None


def _extract_address(driver: Driver) -> Optional[str]:
    """Extract full address from aria-label attribute."""
    try:
        address_selector = '[data-item-id="address"]'
        address_element = _get_element_or_none(driver, address_selector)
        if address_element:
            aria = address_element.get_attribute("aria-label")
            if aria:
                return aria.replace("Address: ", "").replace("Address:", "").strip()

            text = address_element.text
            if text:
                return text.strip()
    except Exception:
        pass
    return None


def _parse_address_components(address: str) -> dict[str, Optional[str]]:
    """Parse address string into city, state, zip_code components."""
    result: dict[str, Optional[str]] = {"city": None, "state": None, "zip_code": None}

    if not address:
        return result

    # Extract zip code
    zip_match = re.search(r"\b(\d{5}(?:-\d{4})?)\b", address)
    if zip_match:
        result["zip_code"] = zip_match.group(1)

    # Extract state: look for 2-letter code immediately before the zip code
    # This avoids matching directional prefixes like NW, SW, SE, NE in street addresses
    state_match = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
    if state_match:
        result["state"] = state_match.group(1)

    # Extract city: the component before "STATE ZIP"
    city_match = re.search(r",\s*([^,]+),\s*[A-Z]{2}\s+\d{5}", address)
    if city_match:
        result["city"] = city_match.group(1).strip()

    return result


def _extract_hours(driver: Driver) -> Optional[dict[str, dict[str, str]]]:
    """Extract hours of operation and return as structured dict."""
    days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    hours_dict: dict[str, dict[str, str]] = {}

    try:
        hours_selector = '[data-item-id="oh"]'
        week_arrow = '[aria-label="Show open hours for the week"]'

        # Scroll to hours section if present
        if driver.is_element_present(hours_selector, wait=2):
            try:
                driver.run_js(
                    f"document.querySelector('{hours_selector}').scrollIntoView({{block: 'center'}})"
                )
                driver.sleep(1)
            except Exception:
                pass

        # Click "Show open hours for the week" arrow
        if driver.is_element_present(week_arrow, wait=2):
            try:
                driver.run_js(f"document.querySelector('{week_arrow}').click()")
                driver.sleep(3)
            except Exception:
                pass

        # Get page HTML after expansion
        html = driver.page_html

        # Extract from hours table
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

        # Fallback - try aria-label on hours element
        if not hours_dict:
            hours_element = _get_element_or_none(driver, hours_selector)
            if hours_element:
                aria = hours_element.get_attribute("aria-label")
                if aria:
                    aria = _normalize_text(aria)
                    closes_match = re.search(
                        r"Closes?\s+(\d{1,2}(?::\d{2})?\s*(?:AM|PM))", aria, re.IGNORECASE
                    )
                    opens_match = re.search(
                        r"Opens?\s+(\d{1,2}(?::\d{2})?\s*(?:AM|PM))", aria, re.IGNORECASE
                    )

                    close_time = (
                        _parse_time_to_24h(closes_match.group(1)) if closes_match else None
                    )
                    open_time = (
                        _parse_time_to_24h(opens_match.group(1)) if opens_match else None
                    )

                    current_day = datetime.now().strftime("%A").lower()

                    if close_time or open_time:
                        hours_dict[current_day] = {
                            "open": open_time if open_time else "unknown",
                            "close": close_time if close_time else "unknown",
                        }

        return hours_dict if hours_dict else None

    except Exception:
        pass

    return None


def _convert_price_range_to_level(low: int, high: int) -> str:
    """Convert price range to $ symbols."""
    avg = (low + high) / 2
    if avg <= 20:
        return "$"
    elif avg <= 35:
        return "$$"
    elif avg <= 60:
        return "$$$"
    return "$$$$"


def _extract_price_level(driver: Driver) -> Optional[str]:
    """Extract price level ($, $$, $$$, $$$$)."""
    try:
        html = driver.page_html

        # $100+ format (very expensive)
        if re.search(r"\$100\+", html):
            return "$$$$"

        # $10-20 or $10–20 format
        price_range = re.search(r"\$(\d+)\s*[–-]\s*(\d+)", html)
        if price_range:
            low = int(price_range.group(1))
            high = int(price_range.group(2))
            return _convert_price_range_to_level(low, high)

        # Price level in aria-label
        price_match = re.search(r'aria-label="[^"]*Price[:\s]*(\$+)', html, re.IGNORECASE)
        if price_match:
            return price_match.group(1)

        # $ symbols between dots
        price_match2 = re.search(r"[·\s](\${1,4})[·\s<]", html)
        if price_match2:
            return price_match2.group(1)

        # $ symbols in span elements
        price_match3 = re.search(r">\s*(\${1,4})\s*<", html)
        if price_match3:
            return price_match3.group(1)

        # Price descriptions
        if re.search(r'aria-label="[^"]*(?:Very\s+)?Expensive', html, re.IGNORECASE):
            return "$$$$" if "Very" in html else "$$$"
        if re.search(r'aria-label="[^"]*Moderate', html, re.IGNORECASE):
            return "$$"
        if re.search(r'aria-label="[^"]*(?:Inexpensive|Cheap)', html, re.IGNORECASE):
            return "$"

    except Exception:
        pass
    return None


def _extract_primary_photo(driver: Driver) -> Optional[str]:
    """Extract primary photo URL."""
    try:
        selectors = [
            "button[jsaction*='heroHeaderImage'] img",
            "button[jsaction*='photo'] img",
            ".RZ66Rb img",
            "img.DSo4Hb",
        ]

        for selector in selectors:
            try:
                element = _get_element_or_none(driver, selector)
                if element:
                    src = element.get_attribute("src")
                    if src and not src.startswith("data:"):
                        return src
            except Exception:
                continue

    except Exception:
        pass
    return None


def _extract_website(driver: Driver) -> Optional[str]:
    """Extract website URL."""
    try:
        website_selector = "a[data-item-id='authority']"
        element = _get_element_or_none(driver, website_selector)
        if element:
            return element.get_attribute("href")
    except Exception:
        pass
    return None


@browser(
    block_images=False,
    cache=True,
    max_retry=3,
    retry_wait=5,
    headless=Config.HEADLESS,
    close_on_crash=True,
    proxy=Config.PROXY_LIST[0] if Config.PROXY_LIST else None,
)
def scrape_place_details(driver: Driver, place_url: str) -> Optional[dict]:
    """
    Scrape detailed information from a Google Maps place page.

    Args:
        driver: Botasaurus browser driver
        place_url: URL to the place page

    Returns:
        Dict with place details or None if skipped/failed
    """
    if not place_url:
        return None

    print(f"\nScraping: {place_url[:80]}...")

    try:
        driver.get(place_url)
        driver.sleep(4)

        _handle_cookie_consent(driver)

        if "consent.google.com" in driver.current_url:
            driver.get(place_url)
            driver.sleep(4)

        place_id = _extract_place_id(place_url)

        # Extract name
        name = None
        try:
            name = driver.get_text("h1")
            if name:
                name = _normalize_text(name)
        except Exception:
            pass

        if not name:
            print("  Warning: Could not extract name, skipping")
            return None

        # Extract rating and apply filter
        rating_text = None
        try:
            rating_text = driver.get_text("div.F7nice > span")
        except Exception:
            pass

        rating = _parse_rating(rating_text)

        if rating is None or rating < Config.MIN_RATING:
            print(f"  Skipping: Rating {rating} is below minimum {Config.MIN_RATING}")
            return None

        # Extract reviews
        reviews_text = None
        try:
            reviews_text = driver.get_text("div.F7nice > span:last-child")
        except Exception:
            pass
        review_count = _parse_review_count(reviews_text)

        # Extract other details
        cuisine_type = _extract_cuisine_type(driver)
        website = _extract_website(driver)
        phone = _extract_phone(driver)
        address = _extract_address(driver)
        lat, lng = _extract_coordinates(driver.current_url)

        hours = _extract_hours(driver)
        price_level = _extract_price_level(driver)
        photo_url = _extract_primary_photo(driver)

        addr_components = _parse_address_components(address)

        result = {
            "place_id": place_id,
            "name": name,
            "business_type": "restaurant",
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

        print(f"  Extracted: {name} ({rating} stars, {review_count} reviews)")
        return result

    except Exception as e:
        print(f"  Error scraping place: {e}")
        return None


@browser(
    block_images=False,
    cache=True,
    max_retry=3,
    retry_wait=5,
    headless=Config.HEADLESS,
    close_on_crash=True,
    parallel=Config.MAX_PARALLEL_BROWSERS or 4,
    reuse_driver=True,
    proxy=Config.PROXY_LIST[0] if Config.PROXY_LIST else None,
)
def _scrape_place_details_parallel(driver: Driver, place_url: str) -> Optional[dict]:
    """Parallel version of scrape_place_details for batch processing."""
    return scrape_place_details.__wrapped__(driver, place_url)


def scrape_places(place_urls: list[str], parallel: bool = True) -> list[dict]:
    """
    Scrape multiple place URLs.

    Args:
        place_urls: List of Google Maps place URLs
        parallel: Whether to run in parallel

    Returns:
        List of place details (None values filtered out)
    """
    if parallel:
        results = _scrape_place_details_parallel(place_urls)
    else:
        results = []
        for url in place_urls:
            result = scrape_place_details(url)
            results.append(result)

    return [r for r in results if r is not None]
