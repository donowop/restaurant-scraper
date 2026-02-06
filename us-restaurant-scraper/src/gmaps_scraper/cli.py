"""Command-line interface for Google Maps Scraper."""

import argparse
import os
import sys

# Load environment variables from .env file
from pathlib import Path
env_file = Path(__file__).parent.parent.parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from gmaps_scraper.config import Config
from gmaps_scraper.checkpoint import CheckpointManager
from gmaps_scraper.deduplication import DeduplicationManager
from gmaps_scraper.scraper import run_scraper


def main() -> int:
    """Entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Scrape US restaurant data from Google Maps"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode with limited queries",
    )
    parser.add_argument(
        "--test-limit",
        type=int,
        default=5,
        help="Number of queries in test mode (default: 5)",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Skip search phase (use existing pending links)",
    )
    parser.add_argument(
        "--skip-details",
        action="store_true",
        help="Skip details phase (only collect links)",
    )
    parser.add_argument(
        "--cities-csv",
        type=str,
        help="Path to cities CSV file",
    )
    parser.add_argument(
        "--zip-codes-csv",
        type=str,
        help="Path to zip codes CSV file",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset all checkpoints and start fresh",
    )
    parser.add_argument(
        "--fill-gaps",
        action="store_true",
        help="Search all remaining zip codes not yet queried (exhaustive coverage)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show query counts, don't scrape",
    )
    parser.add_argument(
        "--cuisine-expansion",
        action="store_true",
        help="Enable cuisine-specific queries for comprehensive coverage",
    )
    parser.add_argument(
        "--cuisine-min-population",
        type=int,
        default=100_000,
        help="Min city population for cuisine expansion (default: 100000)",
    )

    args = parser.parse_args()

    # Reset if requested
    if args.reset:
        print("Resetting all checkpoints...")
        checkpoint = CheckpointManager(Config.CHECKPOINT_DIR)
        checkpoint.reset()
        dedup = DeduplicationManager(
            os.path.join(Config.CHECKPOINT_DIR, "seen_places.json")
        )
        dedup.clear()
        print("Reset complete!")

    # Run scraper
    run_scraper(
        test_mode=args.test,
        test_limit=args.test_limit,
        skip_search=args.skip_search,
        skip_details=args.skip_details,
        cities_csv=args.cities_csv,
        zip_codes_csv=args.zip_codes_csv,
        fill_gaps=args.fill_gaps,
        dry_run=args.dry_run,
        cuisine_expansion=args.cuisine_expansion,
        cuisine_min_population=args.cuisine_min_population,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
