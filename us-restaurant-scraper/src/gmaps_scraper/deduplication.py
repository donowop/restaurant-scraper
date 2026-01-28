"""Deduplication management for restaurant scraping."""

import hashlib
import json
import os
import re
from typing import Optional


class DeduplicationManager:
    """
    Manages deduplication of restaurants using place_id as primary key.
    Falls back to name+address hash if place_id unavailable.
    """

    def __init__(self, storage_path: str = "checkpoints/seen_places.json"):
        self.storage_path = storage_path
        self.seen_place_ids: set[str] = set()
        self.seen_hashes: set[str] = set()
        self._load()

    def _load(self) -> None:
        """Load existing seen IDs from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.seen_place_ids = set(data.get("place_ids", []))
                    self.seen_hashes = set(data.get("hashes", []))
                    print(
                        f"Loaded {len(self.seen_place_ids)} place IDs "
                        f"and {len(self.seen_hashes)} hashes from disk"
                    )
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load dedup data: {e}")
                self.seen_place_ids = set()
                self.seen_hashes = set()

    def _save(self) -> None:
        """Persist seen IDs to disk."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        try:
            with open(self.storage_path, "w") as f:
                json.dump({
                    "place_ids": list(self.seen_place_ids),
                    "hashes": list(self.seen_hashes),
                }, f)
        except IOError as e:
            print(f"Warning: Could not save dedup data: {e}")

    def _compute_hash(self, name: str, address: str) -> str:
        """Compute hash from name and address as fallback identifier."""
        combined = f"{name.lower().strip()}|{address.lower().strip()}"
        return hashlib.md5(combined.encode()).hexdigest()

    def is_duplicate(self, restaurant: dict) -> bool:
        """Check if a restaurant has already been seen."""
        place_id = restaurant.get("place_id")

        # Check place_id first (most reliable)
        if place_id and place_id in self.seen_place_ids:
            return True

        # Fallback to name+address hash
        name = restaurant.get("name", "")
        address = restaurant.get("address", "")
        if name and address:
            hash_key = self._compute_hash(name, address)
            if hash_key in self.seen_hashes:
                return True

        return False

    def mark_seen(self, restaurant: dict) -> None:
        """Mark a restaurant as seen."""
        place_id = restaurant.get("place_id")
        if place_id:
            self.seen_place_ids.add(place_id)

        name = restaurant.get("name", "")
        address = restaurant.get("address", "")
        if name and address:
            hash_key = self._compute_hash(name, address)
            self.seen_hashes.add(hash_key)

    def filter_unique(self, restaurants: list[dict]) -> list[dict]:
        """Filter list to only unique restaurants."""
        unique = []
        for restaurant in restaurants:
            if restaurant is None:
                continue
            if not self.is_duplicate(restaurant):
                unique.append(restaurant)
                self.mark_seen(restaurant)
        return unique

    def is_link_seen(self, link: str) -> bool:
        """Check if a place link has been seen."""
        match = re.search(r"!1s(0x[a-f0-9]+:0x[a-f0-9]+)", link)
        if match:
            place_id = match.group(1)
            return place_id in self.seen_place_ids
        return False

    def filter_unseen_links(self, links: list[str]) -> list[str]:
        """Filter out links to places we've already scraped."""
        return [link for link in links if not self.is_link_seen(link)]

    def save_checkpoint(self) -> None:
        """Save current state to disk."""
        self._save()

    @property
    def count(self) -> int:
        """Number of unique places seen."""
        return len(self.seen_place_ids) + len(self.seen_hashes)

    @property
    def place_id_count(self) -> int:
        """Number of unique place IDs seen."""
        return len(self.seen_place_ids)

    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        return {
            "total_seen": self.count,
            "place_ids": len(self.seen_place_ids),
            "hash_fallbacks": len(self.seen_hashes),
        }

    def clear(self) -> None:
        """Clear all deduplication data."""
        self.seen_place_ids.clear()
        self.seen_hashes.clear()
        self._save()
