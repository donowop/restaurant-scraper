Auto-detect which scraper is active and report its status.

## Detection order
1. Check `us-restaurant-scraper/checkpoints_recovery/progress.json` — if it exists and phase != "complete", this is the active scraper
2. Otherwise check `us-restaurant-scraper/checkpoints/progress.json`

Also run `ps aux | grep -E "recovery_search|rescrape_rejected|gmaps_scraper" | grep -v grep` to check if the process is actually running.

## Recovery scraper (checkpoints_recovery)

### Phase: search

| Metric | Value |
|--------|-------|
| Type | Recovery |
| Phase | Search (re-search) |
| Searches | completed_searches / total_queries (Y%) |
| Pending links | pending_links |
| Process | running or stopped |

### Phase: details

| Metric | Value |
|--------|-------|
| Type | Recovery |
| Phase | Details (scraping restaurants) |
| Details | completed_details / (completed_details + pending_links) (Y%) |
| Saved | total_restaurants_saved restaurants |
| Pending | pending_links links |
| Rate | completed_details / (hours since last restart) per min |
| Process | running or stopped |

## Main scraper (checkpoints)

### Phase: search

| Metric | Value |
|--------|-------|
| Phase | Search (collecting links) |
| Completed | completed_searches_count / 105,184 (Y%) |
| Links Found | total_links_found (X per query) |
| Rate | completed / (hours_running * 60) q/min |
| ETA | (105184 - completed) / rate / 60 hours |

### Phase: details

| Metric | Value |
|--------|-------|
| Phase | Details (saving restaurants) |
| Details | completed_details / (completed_details + pending) |
| Saved | total_restaurants_saved |
| Rate | completed_details / (hours_running * 60) per min |
| ETA | pending / rate hours |

### Phase: complete

Report as complete with final stats. But ALSO check if recovery checkpoint exists with unfinished work — if so, show recovery status instead.

## Calculations
- hours_running = now - started_at (or last_update for recovery)
- Total main queries: 38 cuisines x 2,768 sampled zips = 105,184 (moderate tier)
