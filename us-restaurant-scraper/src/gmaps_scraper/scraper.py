"""Main scraper orchestration for Google Maps restaurant data."""

import json
import os
import time
from datetime import datetime
from typing import Optional

from botasaurus import bt

from gmaps_scraper.config import Config
from gmaps_scraper.checkpoint import CheckpointManager
from gmaps_scraper.deduplication import DeduplicationManager
from gmaps_scraper.geo import get_all_queries, get_test_queries
from gmaps_scraper.geo.locations import (
    generate_remaining_zip_queries,
    generate_cuisine_queries,
    load_cities_from_csv,
)
from gmaps_scraper.extractors import scrape_search_results, scrape_searches, scrape_places


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

        # Filter out already completed queries
        pending_queries = [q for q in batch if not checkpoint.is_search_completed(q.get("query", ""))]

        if not pending_queries:
            print("  All queries in batch already completed, skipping...")
            continue

        # Run searches in parallel
        try:
            results = scrape_searches(pending_queries, parallel=True)
        except Exception as e:
            print(f"  Batch error: {e}")
            for q in pending_queries:
                checkpoint.record_failure(q, str(e))
            continue

        batch_links = []
        for result in results:
            query = result.get("search_data", {}).get("query", "")

            if result and result.get("place_links"):
                links = result["place_links"]
                new_links = dedup.filter_unseen_links(links)
                batch_links.extend(new_links)
                print(f"  {query}: {len(links)} links ({len(new_links)} new)")
            else:
                error = result.get("error") if result else "No result"
                print(f"  {query}: No links found ({error})")

            checkpoint.mark_search_completed(query)

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

    # Load existing results to merge with (preserves previous scrape data)
    final_json = os.path.join(output_dir, "all_restaurants.json")
    all_restaurants = []
    if os.path.exists(final_json):
        try:
            with open(final_json) as f:
                existing = json.load(f)
            if isinstance(existing, list):
                all_restaurants = existing
                for r in all_restaurants:
                    dedup.mark_seen(r)
                print(f"Loaded {len(all_restaurants)} existing restaurants from {final_json}")
        except Exception as e:
            print(f"Warning: Could not load existing results: {e}")

    # Find the max existing batch number to avoid overwriting previous batch files
    existing_batches = [
        int(f.split("_")[-1].split(".")[0])
        for f in os.listdir(output_dir)
        if f.startswith("restaurants_batch_") and f.endswith(".json")
    ] if os.path.exists(output_dir) else []
    batch_num = max(existing_batches) if existing_batches else 0
    progress = checkpoint.get_progress()
    consecutive_empty_batches = 0
    MAX_CONSECUTIVE_EMPTY = 5  # halt after 5 batches with 0 results

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

            # Error rate monitoring: if 0 results from a full batch, something is wrong
            if len(results) == 0 and len(batch) > 0:
                consecutive_empty_batches += 1
                print(f"  WARNING: 0 results from {len(batch)} links! "
                      f"({consecutive_empty_batches}/{MAX_CONSECUTIVE_EMPTY} consecutive)")
                if consecutive_empty_batches >= MAX_CONSECUTIVE_EMPTY:
                    print(f"\n  HALTING: {MAX_CONSECUTIVE_EMPTY} consecutive batches with 0 results.")
                    print("  Browser connections are likely failing. Check cache/reuse_driver settings.")
                    # Don't remove remaining links so they can be retried
                    checkpoint.remove_processed_links(batch)
                    progress["completed_details"] = progress.get("completed_details", 0) + len(batch)
                    progress["total_restaurants_saved"] = len(all_restaurants)
                    checkpoint.save_progress(progress)
                    break
            else:
                consecutive_empty_batches = 0

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


def run_retry_phase(
    checkpoint: CheckpointManager,
    dedup: DeduplicationManager,
    batch_size: Optional[int] = None,
) -> None:
    """
    Phase 3: Retry failed search queries.

    Args:
        checkpoint: CheckpointManager instance
        dedup: DeduplicationManager instance
        batch_size: Number of searches per batch
    """
    if batch_size is None:
        batch_size = Config.SEARCH_BATCH_SIZE

    failures = checkpoint.get_failures()
    # Filter to only search failures (those with 'query' field indicating a search query)
    search_failures = [f for f in failures if isinstance(f.get("item"), dict) and "query" in f.get("item", {})]

    print(f"\n{'='*60}")
    print("PHASE 3: Retry Failed Searches")
    print(f"{'='*60}")
    print(f"Total failures recorded: {len(failures)}")
    print(f"Search failures to retry: {len(search_failures)}")
    print(f"{'='*60}\n")

    if not search_failures:
        print("No search failures to retry!")
        return

    # Extract query data from failures
    queries = [f["item"] for f in search_failures]
    retried_queries = []

    for i in range(0, len(queries), batch_size):
        batch = queries[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(queries) + batch_size - 1) // batch_size

        print(f"\n--- Retry Batch {batch_num}/{total_batches} ({len(batch)} queries) ---")

        batch_links = []
        for query_data in batch:
            query = query_data.get("query", "")

            if checkpoint.is_search_completed(query):
                print(f"  {query}: Already completed, skipping")
                retried_queries.append(query_data)
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
                retried_queries.append(query_data)

            except Exception as e:
                print(f"  {query}: Retry failed - {e}")

        if batch_links:
            added = checkpoint.add_pending_links(batch_links)
            print(f"\nBatch complete: Added {added} new links to pending queue")

        progress = checkpoint.get_progress()
        progress["completed_searches_count"] = checkpoint.get_completed_searches_count()
        progress["total_links_found"] = checkpoint.get_pending_links_count()
        checkpoint.save_progress(progress)
        checkpoint.save_all()
        dedup.save_checkpoint()

        if i + batch_size < len(queries):
            print(f"Waiting {Config.BATCH_DELAY} seconds before next batch...")
            time.sleep(Config.BATCH_DELAY)

    # Remove successfully retried items from failures
    if retried_queries:
        remaining_failures = [
            f for f in failures
            if f.get("item") not in retried_queries
        ]
        # Rewrite failures file with only non-retried items
        checkpoint._save_failures(remaining_failures)
        print(f"\nRetry phase complete! Cleared {len(retried_queries)} retried items from failures")

    new_pending = checkpoint.get_pending_links_count()
    if new_pending > 0:
        print(f"New pending links from retries: {new_pending}")


def run_scraper(
    test_mode: bool = False,
    test_limit: int = 5,
    skip_search: bool = False,
    skip_details: bool = False,
    cities_csv: Optional[str] = None,
    zip_codes_csv: Optional[str] = None,
    fill_gaps: bool = False,
    dry_run: bool = False,
    cuisine_expansion: bool = False,
    cuisine_min_population: int = 100_000,
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
        fill_gaps: Search all remaining zip codes not yet queried
        dry_run: Only show query counts, don't scrape
        cuisine_expansion: Enable cuisine-specific queries for comprehensive coverage
        cuisine_min_population: Min city population for cuisine expansion
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

    if fill_gaps:
        completed_searches = set(checkpoint.get_completed_searches())
        queries = generate_remaining_zip_queries(
            completed_searches=completed_searches,
            cities_csv=cities_csv,
        )
        print(f"\nFill-gaps mode: {len(queries)} remaining zip queries")
        if dry_run:
            print("\nDry run -- no scraping performed.")
            return
    elif cuisine_expansion:
        # Cuisine expansion mode: generate cuisine-specific queries
        completed_searches = set(checkpoint.get_completed_searches())
        # Use default CSV path if not provided
        import os as _os
        csv_path = cities_csv
        if csv_path is None:
            default_csv = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
                "data", "uscities.csv",
            )
            if _os.path.exists(default_csv):
                csv_path = default_csv
        cities = load_cities_from_csv(csv_path, min_population=cuisine_min_population)
        queries = generate_cuisine_queries(
            cities=cities,
            completed_searches=completed_searches,
            min_population=cuisine_min_population,
        )
        print(f"\nCuisine expansion mode: {len(queries)} cuisine-specific queries")
        print(f"  (for cities >= {cuisine_min_population:,} population)")
        if dry_run:
            print("\nDry run -- no scraping performed.")
            return
    elif test_mode:
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
        if dry_run:
            print("\nDry run -- no scraping performed.")
            return

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

    # Phase 3: Retry failed searches
    if not skip_search and checkpoint.get_failures():
        progress = checkpoint.get_progress()
        progress["phase"] = "retry"
        checkpoint.save_progress(progress)
        run_retry_phase(checkpoint, dedup)

        # Run details again if retries found new links
        if not skip_details and checkpoint.get_pending_links_count() > 0:
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
