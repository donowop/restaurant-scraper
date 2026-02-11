"""Post-processing fixes for scraped restaurant data.

Fixes issues that don't require re-scraping:
- State parsing bug (directional prefixes NW/SW/SE/NE parsed as state)
- Missing city extraction
- Restaurant names with embedded addresses/descriptions
"""

import json
import re
import sys
from pathlib import Path


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    "NV",
}


def fix_state(restaurant: dict) -> bool:
    """Fix state field by re-extracting from address. Returns True if changed."""
    address = restaurant.get("address", "")
    current_state = restaurant.get("state")

    if not address:
        return False

    # Extract state code that appears right before the zip code
    match = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
    if match:
        correct_state = match.group(1)
        if correct_state != current_state and correct_state in US_STATES:
            restaurant["state"] = correct_state
            return True

    return False


def fix_city(restaurant: dict) -> bool:
    """Fix missing city by extracting from address. Returns True if changed."""
    if restaurant.get("city"):
        return False

    address = restaurant.get("address", "")
    if not address:
        return False

    match = re.search(r",\s*([^,]+),\s*[A-Z]{2}\s+\d{5}", address)
    if match:
        restaurant["city"] = match.group(1).strip()
        return True

    return False


def fix_name(restaurant: dict) -> bool:
    """Fix names with embedded addresses or descriptions. Returns True if changed."""
    name = restaurant.get("name", "")
    if not name or len(name) <= 50:
        return False

    original = name

    # Remove embedded addresses (city, state zip pattern at end)
    name = re.sub(r"\.\s+[A-Za-z\s]+\b[A-Z]{2}\s+\d{5}.*$", "", name)

    # Remove parenthetical notes like "(Formerly ...)"
    name = re.sub(r"\s*\(Formerly\s+[^)]*\)\s*$", "", name, flags=re.IGNORECASE)

    # Remove pipe-separated service descriptions like "| Dinner, Late Night, ..."
    name = re.sub(r"\s*\|.*$", "", name)

    name = name.strip().rstrip(".")

    if name != original:
        restaurant["name"] = name
        return True

    return False


def run(input_path: str, output_path: str | None = None) -> None:
    """Run all post-processing fixes on the dataset."""
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    with open(input_file) as f:
        restaurants = json.load(f)

    total = len(restaurants)
    state_fixes = 0
    city_fixes = 0
    name_fixes = 0

    for r in restaurants:
        if fix_state(r):
            state_fixes += 1
        if fix_city(r):
            city_fixes += 1
        if fix_name(r):
            name_fixes += 1

    print(f"Processed {total} restaurants:")
    print(f"  State fixes:  {state_fixes}")
    print(f"  City fixes:   {city_fixes}")
    print(f"  Name fixes:   {name_fixes}")

    if output_path is None:
        output_path = input_path

    with open(output_path, "w") as f:
        json.dump(restaurants, f, indent=2)

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "output/all_restaurants.json"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    run(path, out)
