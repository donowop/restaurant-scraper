"""US geographic data and query generation for Google Maps searches."""

import csv
import os
from typing import Optional

from gmaps_scraper.config import Config
from gmaps_scraper.cuisines import CUISINE_TYPES

# Major US cities for testing (top 50 by population)
TEST_CITIES = [
    {"city": "Garden Grove", "state": "CA", "state_name": "California"},
    {"city": "New York", "state": "NY", "state_name": "New York"},
    {"city": "Los Angeles", "state": "CA", "state_name": "California"},
    {"city": "Chicago", "state": "IL", "state_name": "Illinois"},
    {"city": "Houston", "state": "TX", "state_name": "Texas"},
    {"city": "Phoenix", "state": "AZ", "state_name": "Arizona"},
    {"city": "Philadelphia", "state": "PA", "state_name": "Pennsylvania"},
    {"city": "San Antonio", "state": "TX", "state_name": "Texas"},
    {"city": "San Diego", "state": "CA", "state_name": "California"},
    {"city": "Dallas", "state": "TX", "state_name": "Texas"},
    {"city": "San Jose", "state": "CA", "state_name": "California"},
    {"city": "Austin", "state": "TX", "state_name": "Texas"},
    {"city": "Jacksonville", "state": "FL", "state_name": "Florida"},
    {"city": "Fort Worth", "state": "TX", "state_name": "Texas"},
    {"city": "Columbus", "state": "OH", "state_name": "Ohio"},
    {"city": "Charlotte", "state": "NC", "state_name": "North Carolina"},
    {"city": "San Francisco", "state": "CA", "state_name": "California"},
    {"city": "Indianapolis", "state": "IN", "state_name": "Indiana"},
    {"city": "Seattle", "state": "WA", "state_name": "Washington"},
    {"city": "Denver", "state": "CO", "state_name": "Colorado"},
    {"city": "Boston", "state": "MA", "state_name": "Massachusetts"},
    {"city": "Nashville", "state": "TN", "state_name": "Tennessee"},
    {"city": "Detroit", "state": "MI", "state_name": "Michigan"},
    {"city": "Portland", "state": "OR", "state_name": "Oregon"},
    {"city": "Las Vegas", "state": "NV", "state_name": "Nevada"},
    {"city": "Memphis", "state": "TN", "state_name": "Tennessee"},
    {"city": "Louisville", "state": "KY", "state_name": "Kentucky"},
    {"city": "Baltimore", "state": "MD", "state_name": "Maryland"},
    {"city": "Milwaukee", "state": "WI", "state_name": "Wisconsin"},
    {"city": "Albuquerque", "state": "NM", "state_name": "New Mexico"},
    {"city": "Tucson", "state": "AZ", "state_name": "Arizona"},
    {"city": "Fresno", "state": "CA", "state_name": "California"},
    {"city": "Sacramento", "state": "CA", "state_name": "California"},
    {"city": "Mesa", "state": "AZ", "state_name": "Arizona"},
    {"city": "Atlanta", "state": "GA", "state_name": "Georgia"},
    {"city": "Kansas City", "state": "MO", "state_name": "Missouri"},
    {"city": "Colorado Springs", "state": "CO", "state_name": "Colorado"},
    {"city": "Miami", "state": "FL", "state_name": "Florida"},
    {"city": "Raleigh", "state": "NC", "state_name": "North Carolina"},
    {"city": "Omaha", "state": "NE", "state_name": "Nebraska"},
    {"city": "Long Beach", "state": "CA", "state_name": "California"},
    {"city": "Virginia Beach", "state": "VA", "state_name": "Virginia"},
    {"city": "Oakland", "state": "CA", "state_name": "California"},
    {"city": "Minneapolis", "state": "MN", "state_name": "Minnesota"},
    {"city": "Tulsa", "state": "OK", "state_name": "Oklahoma"},
    {"city": "Tampa", "state": "FL", "state_name": "Florida"},
    {"city": "Arlington", "state": "TX", "state_name": "Texas"},
    {"city": "New Orleans", "state": "LA", "state_name": "Louisiana"},
    {"city": "Wichita", "state": "KS", "state_name": "Kansas"},
    {"city": "Cleveland", "state": "OH", "state_name": "Ohio"},
    {"city": "Bakersfield", "state": "CA", "state_name": "California"},
]

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def load_cities_from_csv(filepath: str, min_population: Optional[int] = None) -> list[dict]:
    """
    Load cities from a CSV file, filtered by population.

    Expected CSV format (simplemaps.com):
    city,city_ascii,state_id,state_name,county_fips,county_name,lat,lng,population,...

    Args:
        filepath: Path to the cities CSV file
        min_population: Minimum population threshold (uses Config.MIN_POPULATION if not specified)
    """
    if not os.path.exists(filepath):
        print(f"Warning: Cities CSV not found at {filepath}. Using test cities.")
        return TEST_CITIES

    if min_population is None:
        min_population = getattr(Config, "MIN_POPULATION", 0)

    cities = []
    skipped = 0
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            population = int(row.get("population", 0) or 0)

            # Filter by population
            if min_population and population < min_population:
                skipped += 1
                continue

            cities.append({
                "city": row.get("city", row.get("city_ascii", "")),
                "state": row.get("state_id", ""),
                "state_name": row.get("state_name", ""),
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "population": population,
                "zips": row.get("zips", "").split(),
            })

    # Sort by state priority (NY first, CA second) then by population
    def state_priority(city: dict) -> tuple:
        state = city.get("state", "")
        if state == "NY":
            priority = 0
        elif state == "CA":
            priority = 1
        else:
            priority = 2
        return (priority, -city["population"])  # Negative for descending population

    cities = sorted(cities, key=state_priority)

    if min_population:
        print(f"Loaded {len(cities)} cities with population >= {min_population:,} (skipped {skipped:,} smaller cities)")

    return cities


def load_zip_codes_from_csv(filepath: str) -> list[dict]:
    """
    Load zip codes from a CSV file.

    Expected CSV format:
    zip,lat,lng,city,state_id,state_name,...
    """
    if not os.path.exists(filepath):
        print(f"Warning: Zip codes CSV not found at {filepath}. Skipping zip codes.")
        return []

    zip_codes = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zip_codes.append({
                "zip_code": row.get("zip", row.get("zip_code", "")),
                "lat": row.get("lat", row.get("latitude")),
                "lng": row.get("lng", row.get("longitude")),
                "city": row.get("city", ""),
                "state": row.get("state_id", row.get("state", "")),
            })

    return zip_codes


def generate_city_queries(
    cities: Optional[list[dict]] = None,
    business_type: str = "restaurants",
) -> list[dict]:
    """Generate search queries for all cities."""
    if cities is None:
        cities = TEST_CITIES

    queries = []
    for city in cities:
        city_name = city.get("city", "")
        state = city.get("state_name", city.get("state", ""))

        if not city_name or not state:
            continue

        queries.append({
            "query": f"{business_type} in {city_name}, {state}",
            "city": city_name,
            "state": state,
            "type": "city",
            "lat": city.get("lat"),
            "lng": city.get("lng"),
        })

    return queries


def generate_zip_queries(
    zip_codes: list[dict],
    business_type: str = "restaurants",
) -> list[dict]:
    """Generate search queries for zip codes."""
    queries = []
    for zc in zip_codes:
        zip_code = zc.get("zip_code", "")
        if not zip_code:
            continue

        queries.append({
            "query": f"{business_type} near {zip_code}",
            "zip_code": zip_code,
            "city": zc.get("city", ""),
            "state": zc.get("state", ""),
            "type": "zip",
            "lat": zc.get("lat"),
            "lng": zc.get("lng"),
        })

    return queries


def _get_zip_cap(population: int) -> int:
    """Return max zip code queries for a city based on population tier."""
    for threshold, cap in sorted(Config.ZIP_TIERS.items(), reverse=True):
        if population >= threshold:
            return cap
    return 0


def _get_cuisine_zip_cap(population: int, preset: Optional[str] = None) -> Optional[int]:
    """Return max zip queries for cuisine expansion based on population tier.

    Args:
        population: City population
        preset: Tier preset name ('aggressive', 'moderate', 'conservative', or None for no limit)

    Returns:
        Max zips to sample, or None for no limit
    """
    if preset is None or preset == "none":
        return None

    tiers = Config.CUISINE_ZIP_TIERS.get(preset, Config.CUISINE_ZIP_TIERS.get("moderate", {}))

    for threshold, cap in sorted(tiers.items(), reverse=True):
        if population >= threshold:
            return cap
    return 2  # Default minimum for cities at threshold


def _select_evenly_spaced(items: list, count: int) -> list:
    """Select `count` items evenly spaced from the list for geographic spread."""
    if count <= 0:
        return []
    if count >= len(items):
        return items
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


def generate_zip_queries_from_cities(
    cities: list[dict],
    business_type: str = "restaurants",
) -> list[dict]:
    """Generate zip code queries for large cities using population-tiered caps."""
    queries = []
    for city in cities:
        population = city.get("population", 0)
        cap = _get_zip_cap(population)
        if cap == 0:
            continue

        zips = city.get("zips", [])
        if not zips:
            continue

        selected = _select_evenly_spaced(zips, cap)
        for zip_code in selected:
            queries.append({
                "query": f"{business_type} near {zip_code}",
                "zip_code": zip_code,
                "city": city.get("city", ""),
                "state": city.get("state", ""),
                "type": "zip",
                "lat": city.get("lat"),
                "lng": city.get("lng"),
            })

    return queries


def get_all_queries(
    cities_csv: Optional[str] = None,
    zip_codes_csv: Optional[str] = None,
    include_zip_codes: bool = False,
    business_type: str = "restaurants",
    test_mode: bool = False,
    test_limit: int = 5,
) -> list[dict]:
    """
    Get all search queries for the scraper.

    Args:
        cities_csv: Path to cities CSV file
        zip_codes_csv: Path to zip codes CSV file
        include_zip_codes: Whether to include zip code queries
        business_type: Type of business to search for
        test_mode: If True, only return a limited number of queries
        test_limit: Number of queries to return in test mode

    Returns:
        List of query dicts with metadata
    """
    # Default to bundled data file
    if cities_csv is None:
        default_csv = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data", "uscities.csv",
        )
        if os.path.exists(default_csv):
            cities_csv = default_csv

    # Load cities
    if cities_csv and os.path.exists(cities_csv):
        cities = load_cities_from_csv(cities_csv)
    else:
        cities = TEST_CITIES

    # Generate city queries
    queries = generate_city_queries(cities, business_type)

    # Add zip code queries if requested
    if include_zip_codes:
        if zip_codes_csv:
            zip_codes = load_zip_codes_from_csv(zip_codes_csv)
            queries.extend(generate_zip_queries(zip_codes, business_type))
        else:
            queries.extend(generate_zip_queries_from_cities(cities, business_type))

    # Limit for test mode
    if test_mode:
        queries = queries[:test_limit]

    return queries


def generate_remaining_zip_queries(
    completed_searches: set[str],
    cities_csv: str | None = None,
    business_type: str = "restaurants",
    min_population: int = 50_000,
) -> list[dict]:
    """Generate queries for all zip codes not yet searched.

    Used by --fill-gaps mode to exhaustively search every zip code
    in cities >= min_population that wasn't covered in previous runs.
    """
    if cities_csv is None:
        default_csv = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data", "uscities.csv",
        )
        if os.path.exists(default_csv):
            cities_csv = default_csv

    if not cities_csv or not os.path.exists(cities_csv):
        print("Error: No cities CSV found for fill-gaps mode")
        return []

    cities = load_cities_from_csv(cities_csv, min_population)
    queries = []
    seen_zips: set[str] = set()

    for city in cities:
        zips = city.get("zips", [])
        for zip_code in zips:
            if zip_code in seen_zips:
                continue
            seen_zips.add(zip_code)
            query_str = f"{business_type} near {zip_code}"
            if query_str not in completed_searches:
                queries.append({
                    "query": query_str,
                    "zip_code": zip_code,
                    "city": city.get("city", ""),
                    "state": city.get("state", ""),
                    "type": "zip_fill",
                    "lat": city.get("lat"),
                    "lng": city.get("lng"),
                })

    return queries


def generate_cuisine_queries(
    cities: list[dict],
    completed_searches: set[str],
    min_population: int = 100_000,
    tier_preset: Optional[str] = None,
    use_omitted_only: bool = False,
    omitted_zips_data: Optional[dict] = None,
) -> tuple[list[dict], dict]:
    """Generate cuisine-specific queries for high-population zip codes.

    For each zip code in cities >= min_population, generates queries like:
    - "Thai restaurants near 11201"
    - "Italian restaurants near 11201"
    - etc.

    This surfaces restaurants that don't rank highly in generic searches.

    Args:
        cities: List of city dicts with 'population' and 'zips' fields
        completed_searches: Set of already-completed query strings
        min_population: Only expand cuisines for cities >= this population
        tier_preset: Sampling tier ('aggressive', 'moderate', 'conservative', or None for all)
        use_omitted_only: If True, only query previously omitted zips from omitted_zips_data
        omitted_zips_data: Data from checkpoints/omitted_zips.json for --scrape-omitted mode

    Returns:
        Tuple of (queries list, omitted_info dict for tracking)
    """
    queries = []
    seen_zips: set[str] = set()
    omitted_info: dict = {
        "tier_preset": tier_preset or "none",
        "total_sampled": 0,
        "total_omitted": 0,
        "by_city": {},
    }

    # If using omitted-only mode, get the set of previously omitted zips
    if use_omitted_only and omitted_zips_data:
        omitted_zips_set: set[str] = set()
        for city_data in omitted_zips_data.get("by_city", {}).values():
            omitted_zips_set.update(city_data.get("omitted", []))

        for city in cities:
            if city.get("population", 0) < min_population:
                continue

            for zip_code in city.get("zips", []):
                if zip_code not in omitted_zips_set:
                    continue
                if zip_code in seen_zips:
                    continue
                seen_zips.add(zip_code)

                for cuisine in CUISINE_TYPES:
                    query_str = f"{cuisine} restaurants near {zip_code}"
                    if query_str not in completed_searches:
                        queries.append({
                            "query": query_str,
                            "zip_code": zip_code,
                            "city": city.get("city", ""),
                            "state": city.get("state", ""),
                            "type": "cuisine_zip",
                            "cuisine": cuisine,
                            "lat": city.get("lat"),
                            "lng": city.get("lng"),
                        })

        return queries, omitted_info

    # Build set of extra cities to include regardless of population
    extra_cities_set = set(Config.CUISINE_EXTRA_CITIES) if hasattr(Config, 'CUISINE_EXTRA_CITIES') else set()

    # Normal mode: apply tier-based sampling
    for city in cities:
        city_pop = city.get("population", 0)
        city_tuple = (city.get("city", ""), city.get("state", ""))
        is_extra = city_tuple in extra_cities_set

        if city_pop < min_population and not is_extra:
            continue

        all_zips = city.get("zips", [])
        if not all_zips:
            continue

        city_key = f"{city.get('city', '')}, {city.get('state', '')}"

        # Get cap based on tier preset
        cap = _get_cuisine_zip_cap(city_pop, tier_preset)

        if cap is None or cap >= len(all_zips):
            # No sampling needed - use all zips
            selected_zips = all_zips
            city_omitted: list[str] = []
        else:
            # Sample evenly-spaced zips
            selected_zips = _select_evenly_spaced(all_zips, cap)
            selected_set = set(selected_zips)
            city_omitted = [z for z in all_zips if z not in selected_set]

        # Track omitted zips for this city
        if city_omitted:
            omitted_info["by_city"][city_key] = {
                "population": city_pop,
                "total_zips": len(all_zips),
                "sampled": len(selected_zips),
                "sampled_zips": selected_zips,
                "omitted": city_omitted,
            }
            omitted_info["total_omitted"] += len(city_omitted)

        omitted_info["total_sampled"] += len(selected_zips)

        # Generate queries for selected zips
        for zip_code in selected_zips:
            if zip_code in seen_zips:
                continue
            seen_zips.add(zip_code)

            for cuisine in CUISINE_TYPES:
                query_str = f"{cuisine} restaurants near {zip_code}"
                if query_str not in completed_searches:
                    queries.append({
                        "query": query_str,
                        "zip_code": zip_code,
                        "city": city.get("city", ""),
                        "state": city.get("state", ""),
                        "type": "cuisine_zip",
                        "cuisine": cuisine,
                        "lat": city.get("lat"),
                        "lng": city.get("lng"),
                    })

    return queries, omitted_info


def get_test_queries(limit: int = 5) -> list[dict]:
    """Get a small set of queries for testing."""
    return get_all_queries(test_mode=True, test_limit=limit)
