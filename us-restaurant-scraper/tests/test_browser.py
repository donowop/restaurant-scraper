"""
Browser automation verification test.

Run this first to verify Botasaurus setup works correctly.
"""

import urllib.parse

from botasaurus.browser import browser, Driver


@browser(
    headless=False,  # Visible browser for debugging
    block_images=True,
)
def test_search(driver: Driver, query: str) -> dict:
    """Simple test to verify browser automation works."""
    print(f"\n{'='*50}")
    print("SIMPLE TEST - Watch the browser window!")
    print(f"{'='*50}\n")

    # Go to Google Maps search
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/maps/search/{encoded_query}"

    print(f"1. Opening URL: {url}")
    driver.get(url)

    print("2. Waiting for page to load...")
    driver.sleep(3)

    # Check if the feed (list of results) exists
    feed_selector = '[role="feed"]'
    if driver.is_element_present(feed_selector, wait=5):
        print("3. Found the results list!")
    else:
        print("3. Could not find results list - page may not have loaded")
        return {"success": False, "links": []}

    # Scroll a few times to load more results
    print("4. Scrolling to load more results...")
    for i in range(5):
        driver.scroll(feed_selector)
        driver.sleep(1)
        print(f"   Scroll {i+1}/5 complete")

    # Collect the links
    print("5. Collecting restaurant links...")
    link_selector = '[role="feed"] > div > div > a'
    all_links = driver.get_all_links(link_selector)

    place_links = [link for link in all_links if "/maps/place/" in link]

    print(f"\n{'='*50}")
    print(f"RESULTS: Found {len(place_links)} restaurant links!")
    print(f"{'='*50}\n")

    if place_links:
        print("First 5 links found:")
        for i, link in enumerate(place_links[:5]):
            name = link.split("/maps/place/")[1].split("/")[0].replace("+", " ")
            print(f"  {i+1}. {name[:50]}")

    return {"success": True, "links": place_links, "count": len(place_links)}


def main() -> None:
    """Run the browser test."""
    print("\n" + "=" * 60)
    print("RESTAURANT SCRAPER - BROWSER TEST")
    print("=" * 60)
    print("\nThis will open a Chrome browser window.")
    print("Watch it to see the scraper in action!\n")

    result = test_search("restaurants in Garden Grove, California")

    print("\n" + "=" * 60)
    if result.get("success"):
        print(f"TEST PASSED! Found {result.get('count', 0)} restaurants.")
        print("\nYou're ready to run the full scraper!")
        print("Next step: python -m gmaps_scraper.cli --test --test-limit 1")
    else:
        print("TEST FAILED - Check the browser window for errors")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
