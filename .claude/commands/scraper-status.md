Read `us-restaurant-scraper/checkpoints/progress.json` and report status based on the current phase.

## Phase: search

| Metric | Value |
|--------|-------|
| Phase | Search (collecting links) |
| Completed | completed_searches_count / 105,184 (Y%) |
| Links Found | total_links_found (X per query) |
| Batch | completed/30 of 3,506 |
| Running | hours since started_at |
| Rate | completed / (hours_running * 60) q/min |
| ETA | (105184 - completed) / rate / 60 hours |

Note: total_restaurants_saved = 0 is expected during search phase.

## Phase: details

| Metric | Value |
|--------|-------|
| Phase | Details (saving restaurants) |
| Searches Done | completed_searches_count |
| Details | completed_details / (completed_details + pending) |
| Saved | total_restaurants_saved |
| Rate | completed_details / (hours_running * 60) per min |
| ETA | pending / rate hours |

Read `us-restaurant-scraper/checkpoints/pending_links.json` length for pending count.

## Calculations
- hours_running = now - started_at
- Total queries: 38 cuisines x 2,768 sampled zips = 105,184 (moderate tier)
