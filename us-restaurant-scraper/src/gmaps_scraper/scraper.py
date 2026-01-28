"""Main scraper orchestration for Google Maps restaurant data."""

import os
import time
from datetime import datetime
from typing import Optional

from botasaurus import bt

from gmaps_scraper.config import Config
from gmaps_scraper.checkpoint import CheckpointManager
from gmaps_scraper.deduplication import DeduplicationManager
from gmaps_scraper.geo import get_all_queries, get_test_queries
from gmaps_scraper.extractors import scrape_search_results, scrape_places


def run_search_phase(
    checkpoint: CheckpointManager,
    dedup: DeduplicationManager,
    queries: list[dict],
    batch_size: Optional[int] = None,
) -> None:
    """
    Phase 1: Run searches and collect place links.

    Args:
        checkpoint: CheckpointManager instance
        dedup: DeduplicationManager instance
        queries: List of search queries
        batch_size: Number of searches per batch
    """
    if batch_size is None:
        batch_size = Config.SEARCH_BATCH_SIZE

    remaining = checkpoint.get_remaining_searches(queries)
    total_queries = len(queries)
    completed = total_queries - len(remaining)

    print(f"\n{'='*60}")
    print("PHASE 1: Search Collection")
    print(f"{'='*60}")
    print(f"Total queries: {total_queries}")
    print(f"Already completed: {completed}")
    print(f"Remaining: {len(remaining)}")
    print(f"{'='*60}\n")

    if not remaining:
        print("All searches already completed!")
        return

    for i in range(0, len(remaining), batch_size):
        batch = remaining[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(remaining) + batch_size - 1) // batch_size

        print(f"\n--- Search Batch {batch_num}/{total_batches} ({len(batch)} queries) ---")

        batch_links = []
        for query_data in batch:
            query = query_data.get("query", "")

            if checkpoint.is_search_completed(query):
                continue

            try:
                result = scrape_search_results(query_data)

                if result and result.get("place_links"):
                    links = result["place_links"]
                    new_links = dedup.filter_unseen_links(links)
                    batch_links.extend(new_links)
                    print(f"  {query}: {len(links)} links ({len(new_links)} new)")
                else:
                    error = result.get("error") if result else "No result"
                    print(f"  {query}: No links found ({error})")

                checkpoint.mark_search_completed(query)

            except Exception as e:
                print(f"  {query}: Error - {e}")
                checkpoint.record_failure(query_data, str(e))

        if batch_links:
            added = checkpoint.add_pending_links(batch_links)
            print(f"\nBatch complete: Added {added} new links to pending queue")

        progress = checkpoint.get_progress()
        progress["completed_searches_count"] = checkpoint.get_completed_searches_count()
        progress["total_links_found"] = checkpoint.get_pending_links_count()
        checkpoint.save_progress(progress)
        checkpoint.save_all()
        dedup.save_checkpoint()

        if i + batch_size < len(remaining):
            print(f"Waiting {Config.BATCH_DELAY} seconds before next batch...")
            time.sleep(Config.BATCH_DELAY)

    print(f"\nSearch phase complete! Total pending links: {checkpoint.get_pending_links_count()}")


def run_details_phase(
    checkpoint: CheckpointManager,
    dedup: DeduplicationManager,
    batch_size: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> None:
    """
    Phase 2: Scrape details from place links.

    Args:
        checkpoint: CheckpointManager instance
        dedup: DeduplicationManager instance
        batch_size: Number of places per batch
        output_dir: Directory for output files
    """
    if batch_size is None:
        batch_size = Config.DETAILS_BATCH_SIZE
    if output_dir is None:
        output_dir = Config.OUTPUT_DIR

    os.makedirs(output_dir, exist_ok=True)

    pending_count = checkpoint.get_pending_links_count()

    print(f"\n{'='*60}")
    print("PHASE 2: Detail Scraping")
    print(f"{'='*60}")
    print(f"Pending links: {pending_count}")
    print(f"Batch size: {batch_size}")
    print(f"{'='*60}\n")

    if pending_count == 0:
        print("No pending links to process!")
        return

    all_restaurants = []
    batch_num = 0
    progress = checkpoint.get_progress()

    while True:
        batch = checkpoint.get_next_batch(batch_size)
        if not batch:
            break

        batch_num += 1
        print(f"\n--- Detail Batch {batch_num} ({len(batch)} places) ---")

        try:
            results = scrape_places(batch, parallel=True)
            unique_results = dedup.filter_unique(results)

            if unique_results:
                all_restaurants.extend(unique_results)

                batch_file = os.path.join(output_dir, f"restaurants_batch_{batch_num}.json")
                bt.write_json(unique_results, batch_file)

                print(f"Saved {len(unique_results)} unique restaurants (batch {batch_num})")

            checkpoint.remove_processed_links(batch)

            progress["completed_details"] = progress.get("completed_details", 0) + len(batch)
            progress["total_restaurants_saved"] = len(all_restaurants)
            checkpoint.save_progress(progress)
            dedup.save_checkpoint()

        except Exception as e:
            print(f"Error processing batch: {e}")
            for link in batch:
                checkpoint.record_failure(link, str(e))
            checkpoint.remove_processed_links(batch)

        remaining = checkpoint.get_pending_links_count()
        print(f"Progress: {len(all_restaurants)} restaurants saved, {remaining} links remaining")

        if remaining > 0:
            time.sleep(Config.BATCH_DELAY)

    if all_restaurants:
        final_json = os.path.join(output_dir, "all_restaurants.json")
        final_csv = os.path.join(output_dir, "all_restaurants.csv")

        bt.write_json(all_restaurants, final_json)
        bt.write_csv(all_restaurants, final_csv)

        print(f"\n{'='*60}")
        print("DETAIL SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"Total unique restaurants: {len(all_restaurants)}")
        print(f"Output files:")
        print(f"  - {final_json}")
        print(f"  - {final_csv}")
        print(f"{'='*60}")


def run_scraper(
    test_mode: bool = False,
    test_limit: int = 5,
    skip_search: bool = False,
    skip_details: bool = False,
    cities_csv: Optional[str] = None,
    zip_codes_csv: Optional[str] = None,
) -> None:
    """
    Main scraper orchestration function.

    Args:
        test_mode: Run with limited queries for testing
        test_limit: Number of queries in test mode
        skip_search: Skip search phase (use existing links)
        skip_details: Skip details phase (only collect links)
        cities_csv: Path to cities CSV file
        zip_codes_csv: Path to zip codes CSV file
    """
    print(f"\n{'#'*60}")
    print("US RESTAURANT SCRAPER")
    print(f"{'#'*60}")
    print(f"Started at: {datetime.now().isoformat()}")
    print(f"Test mode: {test_mode}")
    print(f"Min rating filter: {Config.MIN_RATING} stars")
    print(f"{'#'*60}\n")

    checkpoint = CheckpointManager(Config.CHECKPOINT_DIR)
    dedup = DeduplicationManager(os.path.join(Config.CHECKPOINT_DIR, "seen_places.json"))

    stats = checkpoint.get_stats()
    print("Resume stats:")
    print(f"  - Completed searches: {stats['completed_searches']}")
    print(f"  - Pending links: {stats['pending_links']}")
    print(f"  - Restaurants saved: {stats['total_restaurants_saved']}")
    print(f"  - Dedup count: {dedup.count}")

    if test_mode:
        queries = get_test_queries(test_limit)
        print(f"\nTest mode: Using {len(queries)} test queries")
    else:
        queries = get_all_queries(
            cities_csv=cities_csv,
            zip_codes_csv=zip_codes_csv,
            include_zip_codes=Config.INCLUDE_ZIP_CODES,
            business_type="restaurants",
        )
        print(f"\nProduction mode: {len(queries)} total queries")

    # Phase 1: Search
    if not skip_search:
        progress = checkpoint.get_progress()
        progress["phase"] = "search"
        checkpoint.save_progress(progress)
        run_search_phase(checkpoint, dedup, queries)

    # Phase 2: Details
    if not skip_details:
        progress = checkpoint.get_progress()
        progress["phase"] = "details"
        checkpoint.save_progress(progress)
        run_details_phase(checkpoint, dedup)

    # Mark complete
    progress = checkpoint.get_progress()
    progress["phase"] = "complete"
    progress["completed_at"] = datetime.now().isoformat()
    checkpoint.save_progress(progress)

    final_stats = checkpoint.get_stats()
    print(f"\n{'#'*60}")
    print("SCRAPING COMPLETE")
    print(f"{'#'*60}")
    print("Final stats:")
    print(f"  - Searches completed: {final_stats['completed_searches']}")
    print(f"  - Total links found: {final_stats['total_links_found']}")
    print(f"  - Restaurants saved: {final_stats['total_restaurants_saved']}")
    print(f"  - Unique places in dedup: {dedup.count}")
    print(f"  - Failures: {final_stats['failures']}")
    print(f"{'#'*60}\n")
