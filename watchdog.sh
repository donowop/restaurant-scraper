#!/bin/bash
# Generic watchdog: monitors ANY running scraper and kills stale processes.
# Auto-detects: recovery_search, rescrape_rejected, gmaps_scraper
# Checks every 5 minutes. Kills if no checkpoint update in 30 min.
# Does NOT auto-restart — scripts resume from checkpoint when re-launched.

BASE_DIR="/Users/donosclawdbot/repos/restaurant-scraper"
SCRAPER_DIR="$BASE_DIR/us-restaurant-scraper"
WATCHDOG_LOG="$BASE_DIR/logs/watchdog.log"
STALE_SECONDS=1800  # 30 minutes
PYTHON="$SCRAPER_DIR/.venv/bin/python3"

mkdir -p "$(dirname "$WATCHDOG_LOG")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$WATCHDOG_LOG"
}

detect_scraper() {
    # Returns: recovery | rescrape | main | none
    local ps_out
    ps_out=$(ps aux 2>/dev/null)
    if echo "$ps_out" | grep -q "recovery_search\|run_full_recovery"; then
        echo "recovery"
    elif echo "$ps_out" | grep -q "rescrape_rejected"; then
        echo "rescrape"
    elif echo "$ps_out" | grep -v grep | grep -q "gmaps_scraper"; then
        echo "main"
    else
        echo "none"
    fi
}

get_checkpoint() {
    local scraper_type="$1"
    case "$scraper_type" in
        recovery) echo "$SCRAPER_DIR/checkpoints_recovery/progress.json" ;;
        rescrape) echo "$SCRAPER_DIR/checkpoints/rescrape_done.json" ;;
        main)     echo "$SCRAPER_DIR/checkpoints/progress.json" ;;
    esac
}

check_staleness() {
    local checkpoint="$1"
    [ ! -f "$checkpoint" ] && echo "0" && return

    $PYTHON -c "
from datetime import datetime
import json, sys
try:
    p = json.load(open('$checkpoint'))
    last = p.get('last_update', '')
    if not last:
        print('0')
    else:
        secs = int((datetime.now() - datetime.fromisoformat(last)).total_seconds())
        print(secs)
except Exception:
    print('0')
" 2>/dev/null
}

kill_all_scrapers() {
    log "  Killing scraper processes..."
    pkill -f "recovery_search" 2>/dev/null
    pkill -f "rescrape_rejected" 2>/dev/null
    pkill -f "gmaps_scraper" 2>/dev/null
    pkill -f "run_full_recovery" 2>/dev/null
    sleep 2
    pkill -9 -f "recovery_search" 2>/dev/null
    pkill -9 -f "rescrape_rejected" 2>/dev/null
    pkill -9 -f "gmaps_scraper" 2>/dev/null
    pkill -9 -f "chromedriver" 2>/dev/null
    pkill -9 -f "Google Chrome.*bota" 2>/dev/null || true
    sleep 2
    local remaining
    remaining=$(pgrep -f "Google Chrome.*bota" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    log "  Cleanup done. Chrome remaining: $remaining"
}

chrome_count() {
    pgrep -f "Google Chrome.*bota" 2>/dev/null | wc -l | tr -d ' ' || echo "0"
}

send_telegram_alert() {
    local message="$1"
    local bot_token="8569314350:AAFSNpyCVWAVPCEHqg3tyo5q_8J2WDjO2NM"
    local chat_id="-1003515856760"
    local topic_id="18"
    curl -s -X POST "https://api.telegram.org/bot${bot_token}/sendMessage" \
        -d "chat_id=${chat_id}" \
        -d "message_thread_id=${topic_id}" \
        -d "text=${message}" > /dev/null 2>&1
}

# --- Main loop ---
log "Watchdog started (generic mode)"

while true; do
    sleep 300  # check every 5 minutes

    scraper_type=$(detect_scraper)

    if [ "$scraper_type" = "none" ]; then
        # Nothing running — clean up any zombie Chrome
        chrome=$(chrome_count)
        if [ "$chrome" -gt 0 ]; then
            log "No scraper running but $chrome Chrome processes found — cleaning up"
            pkill -9 -f "Google Chrome.*bota" 2>/dev/null || true
        fi
        continue
    fi

    checkpoint=$(get_checkpoint "$scraper_type")
    chrome=$(chrome_count)
    stale_secs=$(check_staleness "$checkpoint")

    # Chrome bloat check (>60 processes)
    if [ "$chrome" -gt 60 ]; then
        log "WARNING: $chrome Chrome processes (scraper=$scraper_type) — killing stale Chrome"
        pkill -9 -f "Google Chrome.*bota" 2>/dev/null || true
        sleep 2
    fi

    # Staleness check
    if [ -n "$stale_secs" ] && [ "$stale_secs" -gt "$STALE_SECONDS" ]; then
        stale_min=$((stale_secs / 60))
        log "STALE: $scraper_type no update in ${stale_min}m (chrome=$chrome) — killing"
        send_telegram_alert "⚠️ WATCHDOG: $scraper_type stalled (${stale_min}m). Killed. Restart manually."
        kill_all_scrapers
    fi
done
