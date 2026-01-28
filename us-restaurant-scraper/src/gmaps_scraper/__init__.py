"""
Google Maps Scraper - A resumable restaurant data scraper.

This package scrapes restaurant data from Google Maps across the United States,
capturing name, cuisine, hours, address, coordinates, ratings, and photos.
"""

from gmaps_scraper.config import Config
from gmaps_scraper.checkpoint import CheckpointManager
from gmaps_scraper.deduplication import DeduplicationManager

__version__ = "1.0.0"
__all__ = ["Config", "CheckpointManager", "DeduplicationManager"]
