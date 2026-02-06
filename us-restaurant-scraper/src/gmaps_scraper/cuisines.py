"""Cuisine types for expanded restaurant searches.

Google Maps returns different results for cuisine-specific queries like
"Thai restaurants near 11201" vs generic "restaurants near 11201".
This allows capturing restaurants that don't rank highly in generic searches.
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
    "Pizza",
    "Sushi",
    "Ramen",
    "Burger",
    "Diner",
    "Tacos",
    "Soup",
    "Noodles",
    # Breakfast/Cafe (often missed in generic searches)
    "Breakfast",
    "Brunch",
    "Bakery",
    "Cafe",
]
