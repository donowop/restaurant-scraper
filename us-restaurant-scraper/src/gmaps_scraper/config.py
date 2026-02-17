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
    # NOTE: Oxylabs proxy is DOWN (connection refused). Do NOT re-enable until fixed.
    USE_PROXIES = False
    PROXY_LIST: list[str] = []

    # Browser settings
    HEADLESS = True  # Production mode

    # Parallelization
    MAX_PARALLEL_BROWSERS = 5  # Sweet spot: 30 q/min with reduced scrolls

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
