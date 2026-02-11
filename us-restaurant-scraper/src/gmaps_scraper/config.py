"""Configuration settings for Google Maps Scraper."""

import os
from datetime import timedelta


class Config:
    """Centralized configuration for the scraper."""

    # Geographic settings
    INCLUDE_ZIP_CODES = True

    # Business type
    BUSINESS_TYPE = "restaurant"

    # Rating filter - only include 3+ stars
    MIN_RATING = 3.0

    # Population filter - only scrape cities with population above this threshold
    MIN_POPULATION = 50000  # ~800 cities, covers all major foodie destinations

    # Batch sizes
    SEARCH_BATCH_SIZE = 30  # Reduced for faster batch sync (was 50)
    DETAILS_BATCH_SIZE = 100

    # Rate limiting
    BATCH_DELAY = 2  # Seconds between batches (reduced from 5)

    # Cache settings
    SEARCH_CACHE_EXPIRY = timedelta(days=7)
    DETAILS_CACHE_EXPIRY = timedelta(days=14)

    # Proxy settings (for large-scale scraping)
    # Set OXYLABS_PROXY_URL environment variable or create .env file
    # NOTE: Proxy disabled - Oxylabs returning connection failures
    USE_PROXIES = False
    PROXY_LIST: list[str] = []
    # PROXY_LIST: list[str] = [
    #     os.environ.get("OXYLABS_PROXY_URL", ""),
    # ] if os.environ.get("OXYLABS_PROXY_URL") else []

    # Browser settings
    HEADLESS = True  # Production mode

    # Parallelization
    MAX_PARALLEL_BROWSERS = 5  # 5 browsers = 30 q/min (sweet spot per testing)

    # Chrome memory management - restart browsers periodically to clear memory leaks
    CHROME_RESTART_INTERVAL = 10  # Restart Chrome every N batches in details phase

    # Output settings
    OUTPUT_DIR = "output"
    CHECKPOINT_DIR = "checkpoints"

    # Zip code query tiers (population threshold -> max zip queries per city)
    ZIP_TIERS = {
        1_000_000: 20,
        500_000: 10,
        200_000: 5,
        100_000: 2,
        50_000: 0,
    }

    # Scroll settings for search results
    MAX_SCROLLS = 7  # Most queries finish in 1-5 scrolls
    SCROLL_DELAY = 0.2  # Faster scrolling

    # Cuisine expansion settings - search with cuisine-specific queries
    # for comprehensive coverage in high-population areas
    ENABLE_CUISINE_EXPANSION = True
    CUISINE_EXPANSION_MIN_POPULATION = 100_000

    # Cuisine zip code tiers - limit zips per city for cuisine expansion
    # Based on population: larger cities get more sampled zips
    # Omitted zips are tracked for optional follow-up scraping
    CUISINE_ZIP_TIERS = {
        "aggressive": {
            8_000_000: 30,   # NYC, LA, Chicago
            5_000_000: 20,   # Miami, Houston, Dallas, Philly, Atlanta, DC
            2_000_000: 15,   # Boston, Phoenix, Detroit, Seattle, SF
            1_000_000: 10,   # Major metros
            500_000: 5,      # Mid-sized cities
            200_000: 3,      # Smaller metros
            100_000: 2,      # Threshold cities
        },
        "moderate": {
            8_000_000: 50,
            5_000_000: 35,
            2_000_000: 25,
            1_000_000: 15,
            500_000: 8,
            200_000: 5,
            100_000: 3,
        },
        "conservative": {
            8_000_000: 80,
            5_000_000: 50,
            2_000_000: 35,
            1_000_000: 25,
            500_000: 15,
            200_000: 8,
            100_000: 5,
        },
    }
    CUISINE_ZIP_TIER_PRESET = "moderate"  # Default preset

    # Cities to include in cuisine expansion even if below population threshold
    # Useful for smaller but notable food destinations
    CUISINE_EXTRA_CITIES = [
        ("Newport Beach", "CA"),
    ]
