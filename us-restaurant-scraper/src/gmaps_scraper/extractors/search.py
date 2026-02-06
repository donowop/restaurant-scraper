"""Search scraper for Google Maps - collects place links from search results."""

import urllib.parse

from botasaurus.browser import browser, Driver
from botasaurus import bt

from gmaps_scraper.config import Config


def _handle_cookie_consent(driver: Driver) -> None:
    """Accept cookies if consent form appears (for European IPs)."""
    if driver.is_in_page("consent.google.com"):
        try:
            agree_selector = "form:nth-child(2) > div > div > button"
            driver.click(agree_selector)
            driver.sleep(1)
        except Exception as e:
            print(f"Warning: Could not accept cookies: {e}")


def _scroll_and_collect_links(
    driver: Driver,
    max_scrolls: int | None = None,
    scroll_delay: float | None = None,
) -> list[str]:
    """
    Scroll through the search results feed until end is reached.

    Returns list of unique place URLs.
    """
    if max_scrolls is None:
        max_scrolls = Config.MAX_SCROLLS
    if scroll_delay is None:
        scroll_delay = Config.SCROLL_DELAY

    collected_links: set[str] = set()
    scroll_count = 0
    no_new_links_count = 0

    feed_selector = '[role="feed"]'
    end_indicator = "p.fontBodyMedium > span > span"
    link_selector = '[role="feed"] > div > div > a'

    # Wait for feed to load
    driver.sleep(1)

    # Check if feed exists
    if not driver.is_element_present(feed_selector):
        print("Warning: Feed not found on page")
        return []

    previous_count = 0

    while scroll_count < max_scrolls:
        # Scroll the feed
        try:
            driver.scroll(feed_selector)
        except Exception as e:
            print(f"Warning: Scroll failed: {e}")
            break

        scroll_count += 1
        driver.sleep(scroll_delay)

        # Collect current links
        try:
            current_links = driver.get_all_links(link_selector)
            for link in current_links:
                if "/maps/place/" in link:
                    collected_links.add(link)
        except Exception as e:
            print(f"Warning: Could not collect links: {e}")

        # Check if we got new links
        if len(collected_links) == previous_count:
            no_new_links_count += 1
        else:
            no_new_links_count = 0
            previous_count = len(collected_links)

        # Stop if no new links after 5 consecutive scrolls
        if no_new_links_count >= 5:
            print(f"No new links after {no_new_links_count} scrolls, stopping")
            break

        # Check if we've reached the end of the list
        if driver.is_element_present(end_indicator):
            print("Reached end of list indicator")
            break

        # Progress logging
        if scroll_count % 10 == 0:
            print(f"Scroll {scroll_count}: {len(collected_links)} links collected")

    print(f"Finished scrolling after {scroll_count} scrolls. Total links: {len(collected_links)}")
    return list(collected_links)


@browser(
    block_images=True,
    cache=False,  # Disabled - was causing stale cached results
    max_retry=3,
    retry_wait=10,
    headless=Config.HEADLESS,
    close_on_crash=True,
)
def scrape_search_results(driver: Driver, search_data: dict) -> dict:
    """
    Scrape Google Maps search results for a given query.

    Args:
        driver: Botasaurus browser driver
        search_data: Dict containing 'query' and optional metadata

    Returns:
        Dict with search_data, place_links, count, and error
    """
    query = search_data.get("query", "")
    if not query:
        return {
            "search_data": search_data,
            "place_links": [],
            "count": 0,
            "error": "No query provided",
        }

    print(f"\n{'='*50}")
    print(f"Searching: {query}")
    print(f"{'='*50}")

    # Build search URL
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/maps/search/{encoded_query}"

    try:
        # Navigate to search page
        driver.get(url)
        driver.sleep(1)

        # Handle cookie consent
        _handle_cookie_consent(driver)

        # If redirected to consent, navigate again
        if "consent.google.com" in driver.current_url:
            driver.get(url)
            driver.sleep(1)

        # Scroll and collect links
        place_links = _scroll_and_collect_links(driver)

        return {
            "search_data": search_data,
            "place_links": place_links,
            "count": len(place_links),
            "error": None,
        }

    except Exception as e:
        print(f"Error scraping search results: {e}")
        return {
            "search_data": search_data,
            "place_links": [],
            "count": 0,
            "error": str(e),
        }


@browser(
    block_images=True,
    cache=False,  # Disabled to prevent cache issues
    max_retry=3,
    retry_wait=10,
    headless=True,
    close_on_crash=True,
    parallel=Config.MAX_PARALLEL_BROWSERS,
    reuse_driver=False,  # Disabled to prevent stale driver connections
)
def _scrape_search_results_parallel(driver: Driver, search_data: dict) -> dict:
    """Parallel version of scrape_search_results for batch processing."""
    return scrape_search_results.__wrapped__(driver, search_data)


def scrape_searches(queries: list[dict], parallel: bool = False) -> list[dict]:
    """
    Scrape multiple search queries.

    Args:
        queries: List of query dicts
        parallel: Whether to run in parallel

    Returns:
        List of results
    """
    if parallel:
        return _scrape_search_results_parallel(queries)

    results = []
    for query in queries:
        result = scrape_search_results(query)
        results.append(result)
    return results
