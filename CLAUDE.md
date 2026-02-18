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
Fields: `completed_searches_count` / 105184, `total_links_found`, `total_restaurants_saved`

Query count: 38 cuisines × 2,768 sampled zips = 105,184 (moderate tier)

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

---

## Scraper Robustness Rules (MANDATORY)
**EVERY scrape script MUST have ALL of these. No exceptions.**

### Browser Decorator Settings
```python
cache=False         # NEVER True — causes "Connection refused", stale data
reuse_driver=False  # NEVER True — causes stale drivers, empty exceptions
```

### Chrome Process Cleanup
- Kill stale Chrome on startup: `pkill -9 -f "Google Chrome.*bota"`
- Check Chrome health every 5-10 batches during execution
- MAX_HEALTHY_CHROME = 60 (5 browsers × ~10 procs each + buffer)
- If over limit, kill all and let botasaurus respawn fresh
- Pattern: `pgrep -f "Google Chrome.*bota"` to count

### Error Rate Monitoring
- Track error rate per batch (None results / batch size)
- Halt after 5 consecutive batches with 80%+ error rate
- Print WARNING with error counts so logs show problems early

### Incremental Saving
- Save results to disk EVERY batch, not just on completion
- Save checkpoint state EVERY batch (done IDs, pending links)
- Crash at batch 500 of 1000 must lose zero completed work

### Pending Links Design
- NEVER remove links from pending until extraction succeeds
- Failed extractions stay in pending for retry

### Telegram Status Updates
- When starting ANY new scrape process, update the Takopi status plugin
  (`takopi_plugins/scraper_status/backend.py`) to read the correct checkpoint
- Also update `.claude/commands/scraper-status.md` if checkpoint paths change
- User monitors progress via hourly Telegram — wrong checkpoint = wrong status

### Commands
```bash
# Start scraper (moderate tier is default)
cd us-restaurant-scraper && PYTHONPATH=src python3 -m gmaps_scraper --cuisine-expansion

# Different tiers: aggressive (~68K), moderate (~105K), conservative (~159K), none (~304K)
PYTHONPATH=src python3 -m gmaps_scraper --cuisine-expansion --cuisine-tier aggressive

# Scrape previously omitted zips (follow-up phase)
PYTHONPATH=src python3 -m gmaps_scraper --cuisine-expansion --scrape-omitted

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

## Repo Organization Rules (MANDATORY)

### Directory Structure
```
restaurant-scraper/
├── CLAUDE.md                      # Project instructions (source of truth)
├── .env                           # Environment variables
├── us-restaurant-scraper/         # Main scraper codebase + venv
├── output/                        # Final results ONLY (all_restaurants.json/csv)
├── logs/                          # ALL log files (scraper logs, watchdog, telegram)
├── takopi_plugins/                # Telegram bot status plugin
├── archive/                       # Old scripts, logs, data — never delete, just archive
├── watchdog.sh                    # Generic watchdog (monitors any running scraper)
├── scraper_telegram_notify.sh     # Hourly Telegram status (uses Takopi plugin)
└── [active scripts]               # Only scripts for current operations
```

### Cleanup Rules
- **Log files**: ALWAYS write to `logs/` directory, never repo root
- **Temporary scripts**: After a one-off task (rescrape, recovery, merge), archive the script
  once it's no longer needed. Don't leave dead scripts at root.
- **Input data files** (recovery links, place IDs, etc.): Archive after the run completes
- **Output batch files**: Only keep final merged result in `output/`. Batches go to archive.
- **When creating new scripts**: Ask "will this be needed for future runs?"
  - Yes → make it generic and keep at root
  - No → plan to archive it after the run

### Infrastructure Reuse
- **watchdog.sh**: Generic — auto-detects recovery/rescrape/main scraper. Applies to ALL runs.
- **scraper_telegram_notify.sh**: Uses Takopi plugin which auto-detects scraper type.
  No manual updates needed per run.
- When implementing a fix for one scraper issue (Chrome cleanup, error monitoring, etc.),
  apply it to ALL active scraper scripts, not just the one that triggered the issue.

### Launchd Agents (~/Library/LaunchAgents/)
- `com.scraper.watchdog` — ACTIVE, runs watchdog.sh (generic, monitors any scraper)
- `com.scraper.telegram` — ACTIVE, hourly Telegram status via Takopi plugin
- `com.scraper.status` — DISABLED (replaced by Takopi)
- `com.scraper.notify` — DISABLED (replaced by Telegram)

---

## Response Style

### Status Format
```
| Metric | Value |
|--------|-------|
| Completed | X / 105,184 (Y%) |
| Links | Z |
| Rate | N q/min |
| ETA | M days |
```

### Optimize
- Don't re-read files in context
- Concise status updates
- Skip known information
