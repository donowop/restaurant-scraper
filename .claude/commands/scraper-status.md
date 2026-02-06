Read `us-restaurant-scraper/checkpoints/progress.json` and report:

| Metric | Value |
|--------|-------|
| Completed | X / 334,666 (Y%) |
| Links Found | Z |
| Rate | completed / (hours_running * 60) q/min |
| Batch | completed/30 of 11,156 |
| ETA | (334666 - completed) / rate / 60 hours |

Calculate hours_running from: now - started_at
