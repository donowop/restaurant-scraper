#!/usr/bin/env python3
"""
Recovery Phase 1 + Phase 2 script.

Re-runs search queries to regenerate pending links that were lost in the
broken cache=True run. Uses seen_places for dedup so only unseen links
are collected and scraped.

Usage:
    cd us-restaurant-scraper
    PYTHONPATH=src python3 -u ../recovery_search.py --query-file ../m1_recovery_queries.json

    # Dry run (Phase 1 only, no detail scraping)
    PYTHONPATH=src python3 -u ../recovery_search.py --query-file ../m1_recovery_queries.json --search-only

    # Skip Phase 1, scrape existing pending links only
    PYTHONPATH=src python3 -u ../recovery_search.py --query-file ../m1_recovery_queries.json --skip-search
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

# Must run from us-restaurant-scraper/ with PYTHONPATH=src
from gmaps_scraper.config import Config
from gmaps_scraper.deduplication import DeduplicationManager
from gmaps_scraper.extractors import scrape_searches, scrape_places

# --- Paths (relative to us-restaurant-scraper/) ---
RECOVERY_CHECKPOINT_DIR = "checkpoints_recovery"
RECOVERY_OUTPUT = "output/recovery_restaurants.json"
MAIN_SEEN_PLACES = os.path.join(Config.CHECKPOINT_DIR, "seen_places.json")

# Recovery checkpoint files
RECOVERY_PROGRESS = os.path.join(RECOVERY_CHECKPOINT_DIR, "progress.json")
RECOVERY_COMPLETED_SEARCHES = os.path.join(RECOVERY_CHECKPOINT_DIR, "completed_searches.json")
RECOVERY_PENDING_LINKS = os.path.join(RECOVERY_CHECKPOINT_DIR, "pending_links.json")


def load_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return default if default is not None else []


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def query_str_to_dict(query_str: str) -> dict:
    """Convert a query string like 'Chinese restaurants near 11229' to a query dict."""
    # Extract zip code from end
    match = re.search(r"near\s+(\d{5})$", query_str)
    zip_code = match.group(1) if match else ""

    # Extract cuisine from beginning
    cuisine_match = re.match(r"^(.+?)\s+restaurants\s+near", query_str)
    cuisine = cuisine_match.group(1) if cuisine_match else ""

    return {
        "query": query_str,
        "zip_code": zip_code,
        "type": "cuisine_zip",
        "cuisine": cuisine,
    }


def run_phase1(query_file: str, dedup: DeduplicationManager):
    """Phase 1: Re-run search queries to collect unseen links."""
    # Load queries
    with open(query_file) as f:
        query_strings = json.load(f)

    print(f"\n{'='*60}")
    print("RECOVERY PHASE 1: Re-search to regenerate lost links")
    print(f"{'='*60}")
    print(f"Total queries in file: {len(query_strings)}")

    # Load completed searches for this recovery run
    completed = set(load_json(RECOVERY_COMPLETED_SEARCHES, []))
    print(f"Already completed (recovery): {len(completed)}")

    # Filter to remaining
    remaining_strs = [q for q in query_strings if q not in completed]
    print(f"Remaining: {len(remaining_strs)}")
    print(f"{'='*60}\n")

    if not remaining_strs:
        print("All recovery searches already completed!")
        return

    # Load existing pending links
    pending_links = set(load_json(RECOVERY_PENDING_LINKS, []))
    print(f"Existing pending links: {len(pending_links)}")

    batch_size = Config.SEARCH_BATCH_SIZE
    total_new_links = 0
    start_time = time.time()

    for i in range(0, len(remaining_strs), batch_size):
        batch_strs = remaining_strs[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(remaining_strs) + batch_size - 1) // batch_size

        # Convert strings to query dicts
        batch_dicts = [query_str_to_dict(q) for q in batch_strs]

        print(f"\n--- Search Batch {batch_num}/{total_batches} ({len(batch_dicts)} queries) ---")

        try:
            results = scrape_searches(batch_dicts, parallel=True)
        except Exception as e:
            print(f"  Batch error: {e}")
            continue

        batch_new = 0
        for result in results:
            query = result.get("search_data", {}).get("query", "")

            if result and result.get("place_links"):
                links = result["place_links"]
                new_links = dedup.filter_unseen_links(links)
                for link in new_links:
                    if link not in pending_links:
                        pending_links.add(link)
                        batch_new += 1
                if new_links:
                    print(f"  {query}: {len(links)} links ({len(new_links)} unseen)")
            else:
                error = result.get("error") if result else "No result"
                print(f"  {query}: 0 links ({error})")

            completed.add(query)

        total_new_links += batch_new

        # Save checkpoint every batch
        save_json(RECOVERY_COMPLETED_SEARCHES, list(completed))
        save_json(RECOVERY_PENDING_LINKS, list(pending_links))

        elapsed = time.time() - start_time
        rate = len(completed) / (elapsed / 60) if elapsed > 0 else 0
        remaining_count = len(remaining_strs) - len(completed) + len(query_strings) - len(remaining_strs)
        # More accurate remaining
        done_this_run = i + len(batch_strs)
        actual_remaining = len(remaining_strs) - done_this_run
        eta_min = actual_remaining / rate if rate > 0 else 0

        print(f"\n  Batch {batch_num}: +{batch_new} new links | "
              f"Total pending: {len(pending_links)} | "
              f"Searches done: {len(completed)}/{len(query_strings)} | "
              f"Rate: {rate:.1f} q/min | ETA: {eta_min/60:.1f} hrs")

        # Save progress
        save_json(RECOVERY_PROGRESS, {
            "phase": "search",
            "completed_searches": len(completed),
            "total_queries": len(query_strings),
            "pending_links": len(pending_links),
            "total_new_links": total_new_links,
            "last_update": datetime.now().isoformat(),
        })

        if i + batch_size < len(remaining_strs):
            time.sleep(Config.BATCH_DELAY)

    print(f"\n{'='*60}")
    print(f"RECOVERY PHASE 1 COMPLETE")
    print(f"Searches completed: {len(completed)}")
    print(f"New unseen links found: {total_new_links}")
    print(f"Total pending links: {len(pending_links)}")
    print(f"{'='*60}\n")


def run_phase2(dedup: DeduplicationManager, links_file: str = None):
    """Phase 2: Scrape details from recovered pending links."""
    if links_file:
        # Load links directly from file (skips Phase 1 entirely)
        with open(links_file) as f:
            links = json.load(f)
        # Merge with any existing pending links
        existing = set(load_json(RECOVERY_PENDING_LINKS, []))
        for link in links:
            existing.add(link)
        pending_links = list(existing)
        save_json(RECOVERY_PENDING_LINKS, pending_links)
        print(f"Loaded {len(links)} links from {links_file}")
    else:
        pending_links = load_json(RECOVERY_PENDING_LINKS, [])

    print(f"\n{'='*60}")
    print("RECOVERY PHASE 2: Scrape details from recovered links")
    print(f"{'='*60}")
    print(f"Pending links: {len(pending_links)}")
    print(f"{'='*60}\n")

    if not pending_links:
        print("No pending links to process!")
        return

    # Load existing recovery results
    os.makedirs(os.path.dirname(RECOVERY_OUTPUT), exist_ok=True)
    all_results = load_json(RECOVERY_OUTPUT, [])
    print(f"Existing recovery results: {len(all_results)}")

    # Mark existing results as seen
    for r in all_results:
        dedup.mark_seen(r)

    batch_size = Config.DETAILS_BATCH_SIZE
    batch_num = 0
    consecutive_empty = 0
    MAX_CONSECUTIVE_EMPTY = 5

    while pending_links:
        batch = pending_links[:batch_size]
        batch_num += 1

        print(f"\n--- Detail Batch {batch_num} ({len(batch)} places) ---")

        try:
            results = scrape_places(batch, parallel=True)

            # Filter None results and non-restaurants
            valid = [r for r in results if r is not None]
            unique = dedup.filter_unique(valid)

            if unique:
                all_results.extend(unique)
                print(f"  Saved {len(unique)} restaurants (total: {len(all_results)})")
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                print(f"  0 results ({consecutive_empty}/{MAX_CONSECUTIVE_EMPTY} consecutive empty)")

            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                print(f"\n  HALTING: {MAX_CONSECUTIVE_EMPTY} consecutive empty batches.")
                break

        except Exception as e:
            print(f"  Error: {e}")

        # Remove processed links regardless (matching current scraper behavior)
        # TODO: Fix this design flaw - should only remove on success
        pending_links = pending_links[batch_size:]

        # Save incrementally
        save_json(RECOVERY_PENDING_LINKS, pending_links)
        save_json(RECOVERY_OUTPUT, all_results)
        dedup.save_checkpoint()

        save_json(RECOVERY_PROGRESS, {
            "phase": "details",
            "completed_details": batch_num * batch_size,
            "pending_links": len(pending_links),
            "total_restaurants_saved": len(all_results),
            "last_update": datetime.now().isoformat(),
        })

        print(f"  Remaining: {len(pending_links)} links")

        if pending_links:
            time.sleep(Config.BATCH_DELAY)

    print(f"\n{'='*60}")
    print(f"RECOVERY PHASE 2 COMPLETE")
    print(f"Total restaurants recovered: {len(all_results)}")
    print(f"Output: {RECOVERY_OUTPUT}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Recovery search for lost links")
    parser.add_argument("--query-file", help="JSON file with list of query strings (required for Phase 1)")
    parser.add_argument("--search-only", action="store_true", help="Only run Phase 1 (search), skip details")
    parser.add_argument("--skip-search", action="store_true", help="Skip Phase 1, only run Phase 2 on existing pending")
    parser.add_argument("--links-file", type=str, help="JSON file with list of URLs for direct Phase 2 (skips Phase 1)")
    args = parser.parse_args()

    os.makedirs(RECOVERY_CHECKPOINT_DIR, exist_ok=True)

    # Use the MAIN seen_places.json for dedup (shared with main scraper)
    dedup = DeduplicationManager(MAIN_SEEN_PLACES)
    print(f"Dedup loaded: {dedup.place_id_count} place_ids, {len(dedup.seen_hashes)} hashes")

    if args.links_file:
        # Direct Phase 2 from links file (no Phase 1 needed)
        run_phase2(dedup, links_file=args.links_file)
    else:
        if not args.skip_search:
            run_phase1(args.query_file, dedup)

        if not args.search_only:
            run_phase2(dedup)


if __name__ == "__main__":
    main()
