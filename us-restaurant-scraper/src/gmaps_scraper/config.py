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
    SEARCH_BATCH_SIZE = 50
    DETAILS_BATCH_SIZE = 100

    # Rate limiting
    BATCH_DELAY = 5  # Seconds between batches

    # Cache settings
    SEARCH_CACHE_EXPIRY = timedelta(days=7)
    DETAILS_CACHE_EXPIRY = timedelta(days=14)

    # Proxy settings (for large-scale scraping)
    # Set OXYLABS_PROXY_URL environment variable or create .env file
    USE_PROXIES = True
    PROXY_LIST: list[str] = [
        os.environ.get("OXYLABS_PROXY_URL", ""),
    ] if os.environ.get("OXYLABS_PROXY_URL") else []

    # Browser settings
    HEADLESS = True  # Production mode

    # Parallelization
    MAX_PARALLEL_BROWSERS = 4

    # Output settings
    OUTPUT_DIR = "output"
    CHECKPOINT_DIR = "checkpoints"

    # Scroll settings for search results
    MAX_SCROLLS = 100
    SCROLL_DELAY = 0.5
