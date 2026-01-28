# US Restaurant Scraper - Setup Guide

## Overview
This scraper collects restaurant data from Google Maps across all US cities. This guide covers proxy setup, city data, and running the scraper.

---

## 1. City Data Setup

### Option A: SimpleMaps (Recommended - Free)
1. Go to: https://simplemaps.com/data/us-cities
2. Download the **free** version (includes ~30,000 cities)
3. You'll get `uscities.csv` with columns: city, state_id, state_name, lat, lng, population, etc.
4. Place the file in: `us-restaurant-scraper/data/uscities.csv`

### Option B: US Census Data (Official)
1. Go to: https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html
2. Download "Places" gazetteer file
3. Contains all census-designated places (~30,000+)

### Current Implementation
The scraper already has `data/locations.py` that generates queries. After downloading city data, update the file to load from CSV:

```python
# In data/locations.py, add:
import csv

def load_cities_from_csv():
    cities = []
    with open('data/uscities.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cities.append({
                'city': row['city'],
                'state': row['state_id'],
                'population': int(row['population'] or 0)
            })
    # Sort by population (largest first) for better coverage
    return sorted(cities, key=lambda x: x['population'], reverse=True)
```

---

## 2. Proxy Setup

### Why Proxies Are Needed
- Google rate-limits and blocks IPs that make too many requests
- Residential proxies appear as regular home internet users
- Essential for scraping 40,000+ cities without getting blocked

### Recommended Providers (by price)

| Provider | Price | Notes |
|----------|-------|-------|
| **IPRoyal** | ~$5/GB | Budget option, good for testing |
| **SmartProxy** | ~$8/GB | Good US coverage |
| **Oxylabs** | ~$12/GB | Reliable, good rotation |
| **Bright Data** | ~$15/GB | Industry standard, most reliable |

### Estimated Costs
- ~40,000 city searches × ~50KB each = ~2GB for searches
- ~500,000 restaurant pages × ~200KB each = ~100GB for details
- **Total estimate: $500-1500** depending on provider and actual restaurant count

### Setup Steps

#### Step 1: Sign up for a proxy provider
Choose one from above. Most offer pay-as-you-go or monthly plans.

#### Step 2: Get your proxy credentials
You'll receive something like:
```
Host: us.smartproxy.com
Port: 10000
Username: your_username
Password: your_password
```

#### Step 3: Configure the scraper
Edit `config.py`:

```python
# Proxy settings
USE_PROXIES = True
PROXY_LIST = [
    "http://username:password@us.smartproxy.com:10000",
    # Add more proxy endpoints for rotation
]
```

#### Step 4: For rotating proxies (recommended)
Most providers give you a single endpoint that auto-rotates IPs:
```python
PROXY_LIST = [
    "http://username:password@gate.smartproxy.com:7000",
]
```

### Testing Your Proxy
```bash
# Test proxy works
curl -x "http://username:password@proxy.example.com:port" https://httpbin.org/ip
```

---

## 3. Running the Scraper

### Pre-flight Checklist
- [ ] City data CSV downloaded and placed in `data/`
- [ ] Proxies configured in `config.py` (or set `USE_PROXIES = False` for testing)
- [ ] `HEADLESS = True` in `config.py` for production
- [ ] Sufficient disk space (~50GB for full US scrape)

### Test Run (Recommended First)
```bash
cd /Users/dono/repos/botasaurus/us-restaurant-scraper

# Edit main.py to limit cities for testing
# Change: cities = get_all_cities()[:5]  # Only first 5 cities

python3 main.py
```

### Full Production Run
```bash
cd /Users/dono/repos/botasaurus/us-restaurant-scraper
python3 main.py
```

### Monitoring Progress
- Check `output/` for saved results
- Check `checkpoints/` for progress (allows resume if interrupted)
- Logs show: city being searched, restaurants found, extraction status

### Resume After Interruption
The scraper auto-saves checkpoints. Just run `python3 main.py` again and it will resume where it left off.

---

## 4. After the Scrape

### Analyze Results
```python
import json

with open('output/all_restaurants.json', 'r') as f:
    data = json.load(f)

# Count missing data
missing_price = [r for r in data if r.get('price_level') is None]
missing_hours = [r for r in data if not r.get('hours_of_operation') or len(r.get('hours_of_operation', {})) < 7]

print(f"Total restaurants: {len(data)}")
print(f"Missing price: {len(missing_price)} ({100*len(missing_price)/len(data):.1f}%)")
print(f"Incomplete hours: {len(missing_hours)} ({100*len(missing_hours)/len(data):.1f}%)")
```

### Targeted Re-scrape for Missing Data
After the main scrape, create a list of restaurants needing re-scrape:
```python
# Extract URLs for re-scrape
rescrape_urls = [r['google_maps_url'] for r in data if r.get('price_level') is None]

with open('output/rescrape_urls.json', 'w') as f:
    json.dump(rescrape_urls, f)
```

Then run targeted scrape with cookies (see Section 5).

---

## 5. Authenticated Re-scrape (For Missing Data)

Google shows more data to logged-in users. To scrape with authentication:

### Option A: Export Chrome Cookies

1. Install browser extension: "EditThisCookie" or "Cookie-Editor"
2. Log into Google Maps in Chrome
3. Export cookies as JSON
4. Save to `us-restaurant-scraper/google_cookies.json`

### Option B: Use Chrome Profile

1. Find your Chrome profile path:
   - Mac: `~/Library/Application Support/Google/Chrome/Default`
   - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data\Default`

2. Update scraper to use profile:
```python
@browser(
    user_data_dir="path/to/chrome/profile",
    # ... other options
)
```

### Create Targeted Re-scrape Script
```python
# rescrape_missing.py
from botasaurus.browser import browser, Driver
import json

# Load cookies
with open('google_cookies.json', 'r') as f:
    cookies = json.load(f)

@browser(
    headless=True,
    # Add cookies after page load
)
def rescrape_with_cookies(driver: Driver, url: str):
    driver.get("https://www.google.com/maps")

    # Inject cookies
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass

    # Now scrape the actual URL
    driver.get(url)
    # ... extraction logic
```

---

## 6. Config Reference

### config.py Settings

```python
class Config:
    # Geographic settings
    INCLUDE_ZIP_CODES = True      # Also search by zip code for complete coverage

    # Business type
    BUSINESS_TYPE = "restaurant"

    # Rating filter
    MIN_RATING = 3.0              # Skip restaurants below 3 stars

    # Batch sizes
    SEARCH_BATCH_SIZE = 50        # Searches per batch
    DETAILS_BATCH_SIZE = 100      # Place details per batch

    # Rate limiting
    BATCH_DELAY = 5               # Seconds between batches

    # Proxy settings
    USE_PROXIES = False           # Set True when proxies ready
    PROXY_LIST = []               # Add proxy URLs here

    # Browser settings
    HEADLESS = True               # True for production
    MAX_PARALLEL_BROWSERS = 4     # Concurrent browsers (4 is safe)

    # Output
    OUTPUT_DIR = "output"
    CHECKPOINT_DIR = "checkpoints"
```

---

## 7. Troubleshooting

### "Chrome connection failed"
- Reduce `MAX_PARALLEL_BROWSERS` to 2-3
- Kill stale Chrome processes: `pkill -f chrome`

### Getting blocked by Google
- Enable proxies
- Reduce parallel browsers
- Increase `BATCH_DELAY`

### Missing data (price/hours)
- Expected for ~10% without authentication
- Use authenticated re-scrape (Section 5)

### Scraper crashes mid-run
- Check `checkpoints/` folder
- Just run `python3 main.py` again to resume

---

## 8. Expected Timeline

| Phase | Duration | Notes |
|-------|----------|-------|
| Test run (5 cities) | 30 min | Verify everything works |
| Search phase | 3-5 days | Collect all restaurant URLs |
| Details phase | 2-3 weeks | Scrape each restaurant |
| Re-scrape missing | 2-3 days | Fill in gaps with cookies |

**Total: 3-4 weeks** for complete US coverage with proper infrastructure.

---

## Quick Start Commands

```bash
# Navigate to scraper
cd /Users/dono/repos/botasaurus/us-restaurant-scraper

# Test run (edit main.py to limit cities first)
python3 main.py

# Check output
ls -la output/

# Count results
python3 -c "import json; d=json.load(open('output/all_restaurants.json')); print(f'Total: {len(d)}')"
```
