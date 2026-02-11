"""Cuisine types for expanded restaurant searches.

Google Maps returns different results for cuisine-specific queries like
"Thai restaurants near 11201" vs generic "restaurants near 11201".
This allows capturing restaurants that don't rank highly in generic searches.

Note: Removed redundant sub-cuisines that overlap with parent categories:
- Sushi, Ramen (covered by Japanese)
- Tacos (covered by Mexican)
- Pizza (covered by Italian)
- Burger (covered by American)
- Brunch (covered by Breakfast + Cafe)
"""

CUISINE_TYPES = [
    # Asian
    "Chinese",
    "Japanese",
    "Thai",
    "Vietnamese",
    "Korean",
    "Indian",
    "Filipino",
    "Malaysian",
    "Taiwanese",
    # European
    "Italian",
    "French",
    "Greek",
    "Spanish",
    "German",
    # Latin American
    "Mexican",
    "Brazilian",
    "Peruvian",
    "Cuban",
    "Colombian",
    # Middle Eastern / Mediterranean
    "Mediterranean",
    "Middle Eastern",
    "Turkish",
    "Lebanese",
    # American
    "American",
    "Southern",
    "BBQ",
    "Cajun",
    "Soul food",
    # Categories
    "Seafood",
    "Steakhouse",
    "Vegetarian",
    "Vegan",
    "Diner",
    "Soup",
    "Noodles",
    # Breakfast/Cafe (often missed in generic searches)
    "Breakfast",
    "Bakery",
    "Cafe",
]
