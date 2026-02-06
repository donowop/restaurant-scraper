# Claude Code Preferences

## Automation
- Make file changes directly - never ask user to manually edit
- Automate everything; execute directly without asking

---

## Scraper Quick Reference

### Status Check
```bash
cat us-restaurant-scraper/checkpoints/progress.json
```
Fields: `completed_searches_count` / 334666, `total_links_found`, `total_restaurants_saved`

Rate = completed / (hours * 60) q/min | ETA = remaining / rate / 60 hours

### Architecture
- **Phase 1 (Search)**: Collects place links, NO proxy, 5 browsers parallel
- **Phase 2 (Details)**: Visits each link, USES proxy, extracts restaurant data
- Processing order: Cities by population (NYC first)
- **Why sequential phases?** Same restaurant appears in multiple cuisine queries. Deduplicating BEFORE details phase saves proxy bandwidth and time.

### Config (config.py) - Optimized
```
MAX_PARALLEL_BROWSERS = 5   # Sweet spot: 30 q/min (6+ browsers causes sync overhead)
MAX_SCROLLS = 7             # Most queries finish in 1-5 scrolls
SCROLL_DELAY = 0.2          # Faster scrolling
BATCH_DELAY = 2
SEARCH_BATCH_SIZE = 30      # Smaller batches = faster sync
```

### Performance Findings
- **5 browsers = 30 q/min** (sweet spot)
- 6 browsers = 15 q/min (batch sync overhead)
- 8-10 browsers = unstable/stalls
- `cache=False` required on @browser decorators (prevents Connection refused errors)
- `reuse_driver=False` required (prevents stale driver connections)

### Commands
```bash
# Start scraper
cd us-restaurant-scraper && PYTHONPATH=src python3 -m gmaps_scraper --cuisine-expansion

# Dry run
PYTHONPATH=src python3 -m gmaps_scraper --cuisine-expansion --dry-run

# Browser count
ps aux | grep -i chrome | grep -v grep | wc -l
```

### Key Files
- `checkpoints/progress.json` - phase, counts
- `checkpoints/completed_searches.json` - done queries
- `checkpoints/pending_links.json` - links for phase 2
- `output/all_restaurants.json` - final data

---

## Response Style

### Status Format
```
| Metric | Value |
|--------|-------|
| Completed | X / 334,666 (Y%) |
| Links | Z |
| Rate | N q/min |
| ETA | M days |
```

### Optimize
- Don't re-read files in context
- Concise status updates
- Skip known information
