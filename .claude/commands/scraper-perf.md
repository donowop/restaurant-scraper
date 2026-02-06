Measure actual scraper performance:

1. Read `us-restaurant-scraper/checkpoints/progress.json` - record completed_searches_count as T1
2. Wait 2 minutes
3. Read again - record as T2
4. Calculate: rate = (T2 - T1) / 2 q/min

Compare to targets:
- Baseline: 4.6 q/min (before optimization)
- Current optimal: 30 q/min (5 browsers, MAX_SCROLLS=7, SCROLL_DELAY=0.2)
- Warning threshold: < 20 q/min

If rate < 20: Check Chrome process count (should be ~27 for 5 browsers). If low, scraper may have stalled.
