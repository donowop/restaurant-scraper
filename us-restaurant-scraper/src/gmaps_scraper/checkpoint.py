"""Checkpoint management for resumable scraping operations."""

import json
import os
from datetime import datetime
from typing import Any, Optional


class CheckpointManager:
    """
    Manages progress checkpoints for resumable scraping.

    Tracks:
    - Current phase (search, details, complete)
    - Completed searches
    - Pending place links
    - Failed items for retry
    """

    def __init__(self, checkpoint_dir: str = "checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

        self._progress_file = os.path.join(checkpoint_dir, "progress.json")
        self._pending_links_file = os.path.join(checkpoint_dir, "pending_links.json")
        self._failed_items_file = os.path.join(checkpoint_dir, "failed_items.json")
        self._completed_searches_file = os.path.join(checkpoint_dir, "completed_searches.json")

        # In-memory cache
        self._completed_searches: Optional[set[str]] = None
        self._pending_links: Optional[list[str]] = None

    def get_progress(self) -> dict:
        """Load current progress."""
        if os.path.exists(self._progress_file):
            try:
                with open(self._progress_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "phase": "search",
            "completed_searches_count": 0,
            "completed_details": 0,
            "total_links_found": 0,
            "total_restaurants_saved": 0,
            "last_update": None,
            "started_at": datetime.now().isoformat(),
        }

    def save_progress(self, progress: dict) -> None:
        """Save progress checkpoint."""
        progress["last_update"] = datetime.now().isoformat()
        try:
            with open(self._progress_file, "w") as f:
                json.dump(progress, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save progress: {e}")

    def _load_completed_searches(self) -> set[str]:
        """Load completed searches from disk."""
        if os.path.exists(self._completed_searches_file):
            try:
                with open(self._completed_searches_file, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass
        return set()

    def _save_completed_searches(self) -> None:
        """Save completed searches to disk."""
        if self._completed_searches is not None:
            try:
                with open(self._completed_searches_file, "w") as f:
                    json.dump(list(self._completed_searches), f)
            except IOError as e:
                print(f"Warning: Could not save completed searches: {e}")

    def mark_search_completed(self, query: str) -> None:
        """Mark a search query as completed."""
        if self._completed_searches is None:
            self._completed_searches = self._load_completed_searches()
        self._completed_searches.add(query)

    def is_search_completed(self, query: str) -> bool:
        """Check if a search query has been completed."""
        if self._completed_searches is None:
            self._completed_searches = self._load_completed_searches()
        return query in self._completed_searches

    def get_completed_searches(self) -> set[str]:
        """Get the set of completed search query strings."""
        if self._completed_searches is None:
            self._completed_searches = self._load_completed_searches()
        return self._completed_searches

    def get_completed_searches_count(self) -> int:
        """Get count of completed searches."""
        if self._completed_searches is None:
            self._completed_searches = self._load_completed_searches()
        return len(self._completed_searches)

    def get_remaining_searches(self, all_queries: list[dict]) -> list[dict]:
        """Get search queries that haven't been completed."""
        if self._completed_searches is None:
            self._completed_searches = self._load_completed_searches()
        return [q for q in all_queries if q.get("query") not in self._completed_searches]

    def add_pending_links(self, links: list[str]) -> int:
        """Add links to pending queue. Returns number of new links added."""
        existing = set(self.get_pending_links())
        new_links = [link for link in links if link not in existing]

        if new_links:
            combined = list(existing) + new_links
            try:
                with open(self._pending_links_file, "w") as f:
                    json.dump(combined, f)
                self._pending_links = combined
            except IOError as e:
                print(f"Warning: Could not save pending links: {e}")

        return len(new_links)

    def get_pending_links(self) -> list[str]:
        """Get all pending links."""
        if self._pending_links is not None:
            return self._pending_links

        if os.path.exists(self._pending_links_file):
            try:
                with open(self._pending_links_file, "r") as f:
                    self._pending_links = json.load(f)
                    return self._pending_links
            except (json.JSONDecodeError, IOError):
                pass

        self._pending_links = []
        return self._pending_links

    def get_pending_links_count(self) -> int:
        """Get count of pending links."""
        return len(self.get_pending_links())

    def remove_processed_links(self, links: list[str]) -> None:
        """Remove processed links from pending."""
        links_set = set(links)
        pending = self.get_pending_links()
        remaining = [link for link in pending if link not in links_set]

        try:
            with open(self._pending_links_file, "w") as f:
                json.dump(remaining, f)
            self._pending_links = remaining
        except IOError as e:
            print(f"Warning: Could not update pending links: {e}")

    def get_next_batch(self, batch_size: int) -> list[str]:
        """Get next batch of links to process."""
        return self.get_pending_links()[:batch_size]

    def record_failure(self, item: Any, error: str) -> None:
        """Record a failed item for retry."""
        failures = []
        if os.path.exists(self._failed_items_file):
            try:
                with open(self._failed_items_file, "r") as f:
                    failures = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        failures.append({
            "item": item,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

        try:
            with open(self._failed_items_file, "w") as f:
                json.dump(failures, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not record failure: {e}")

    def get_failures(self) -> list[dict]:
        """Get all recorded failures."""
        if os.path.exists(self._failed_items_file):
            try:
                with open(self._failed_items_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def clear_failures(self) -> None:
        """Clear all recorded failures."""
        if os.path.exists(self._failed_items_file):
            try:
                os.remove(self._failed_items_file)
            except IOError:
                pass

    def _save_failures(self, failures: list[dict]) -> None:
        """Save failures list to disk (used for updating after retries)."""
        try:
            with open(self._failed_items_file, "w") as f:
                json.dump(failures, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save failures: {e}")

    def save_all(self) -> None:
        """Save all checkpoint data to disk."""
        self._save_completed_searches()

    def get_stats(self) -> dict:
        """Get checkpoint statistics."""
        progress = self.get_progress()
        return {
            "phase": progress.get("phase", "search"),
            "completed_searches": self.get_completed_searches_count(),
            "pending_links": self.get_pending_links_count(),
            "total_links_found": progress.get("total_links_found", 0),
            "total_restaurants_saved": progress.get("total_restaurants_saved", 0),
            "failures": len(self.get_failures()),
            "last_update": progress.get("last_update"),
            "started_at": progress.get("started_at"),
        }

    def reset(self) -> None:
        """Reset all checkpoint data."""
        self._completed_searches = set()
        self._pending_links = []

        files_to_remove = [
            self._progress_file,
            self._pending_links_file,
            self._failed_items_file,
            self._completed_searches_file,
        ]

        for filepath in files_to_remove:
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except IOError:
                    pass
