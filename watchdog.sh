#!/bin/bash
# Generic watchdog: monitors ANY running scraper, kills stale processes, auto-restarts.
# Auto-detects: recovery (run_full_recovery.sh), rescrape_rejected, gmaps_scraper
# Checks every 5 minutes. Kills + restarts if no checkpoint update in 30 min.

BASE_DIR="/Users/donosclawdbot/repos/restaurant-scraper"
SCRAPER_DIR="$BASE_DIR/us-restaurant-scraper"
WATCHDOG_LOG="$BASE_DIR/logs/watchdog.log"
STALE_SECONDS=1800  # 30 minutes
PYTHON="$SCRAPER_DIR/.venv/bin/python3"
LAST_RESTART_FILE="$BASE_DIR/logs/.watchdog_last_restart"
LAST_SCRAPER_FILE="$BASE_DIR/logs/.watchdog_last_scraper"

mkdir -p "$(dirname "$WATCHDOG_LOG")"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$WATCHDOG_LOG"
}

detect_scraper() {
    # Returns: recovery | rescrape | main | none
    # IMPORTANT: use grep -E for alternation. BSD grep \| is unreliable on macOS.
    # Check recovery FIRST — recovery_search imports gmaps_scraper, so "gmaps_scraper"
    # appears in worker processes even during recovery. Must not fall through to "main".
    local ps_out
    ps_out=$(ps aux 2>/dev/null)
    if echo "$ps_out" | grep -E -q "recovery_search|run_full_recovery"; then
        echo "recovery"
    elif echo "$ps_out" | grep -q "rescrape_rejected"; then
        echo "rescrape"
    elif echo "$ps_out" | grep -v grep | grep -E -q "\-m gmaps_scraper|gmaps_scraper.cli"; then
        echo "main"
    else
        echo "none"
    fi
}

detect_machine() {
    # Detect m1 or m2 from running process args or existing data files
    local ps_out
    ps_out=$(ps aux 2>/dev/null)
    if echo "$ps_out" | grep -E -q "m2_|m2 "; then
        echo "m2"
    elif echo "$ps_out" | grep -E -q "m1_|m1 "; then
        echo "m1"
    elif [ -f "$BASE_DIR/m1_recovery_links.json" ]; then
        echo "m1"
    elif [ -f "$BASE_DIR/m2_recovery_links.json" ]; then
        echo "m2"
    else
        echo "m1"  # default
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

restart_scraper() {
    local scraper_type="$1"
    local machine
    machine=$(detect_machine)

    # Prevent rapid restart loops: min 10 min between restarts
    if [ -f "$LAST_RESTART_FILE" ]; then
        local last_restart
        last_restart=$(cat "$LAST_RESTART_FILE")
        local now
        now=$(date +%s)
        local diff=$(( now - last_restart ))
        if [ "$diff" -lt 600 ]; then
            log "  Skipping restart — last restart was ${diff}s ago (min 600s)"
            return
        fi
    fi
    date +%s > "$LAST_RESTART_FILE"

    # Touch checkpoint last_update so the stale check gives the new process time
    local checkpoint
    checkpoint=$(get_checkpoint "$scraper_type")
    if [ -n "$checkpoint" ] && [ -f "$checkpoint" ]; then
        $PYTHON -c "
import json
from datetime import datetime
try:
    with open('$checkpoint') as f:
        p = json.load(f)
    p['last_update'] = datetime.now().isoformat()
    with open('$checkpoint', 'w') as f:
        json.dump(p, f)
except: pass
" 2>/dev/null
        log "  Updated checkpoint last_update to now"
    fi

    case "$scraper_type" in
        recovery)
            log "  Restarting: run_full_recovery.sh $machine"
            cd "$BASE_DIR"
            nohup ./run_full_recovery.sh "$machine" >> "$BASE_DIR/logs/recovery_${machine}.log" 2>&1 &
            log "  Started PID $!"
            ;;
        rescrape)
            local rescrape_file="$BASE_DIR/${machine}_rescrape_place_ids.json"
            if [ -f "$rescrape_file" ]; then
                log "  Restarting: rescrape_rejected.py ($machine)"
                cd "$SCRAPER_DIR"
                PYTHONPATH=src nohup "$PYTHON" -u ../rescrape_rejected.py --place-ids-file "$rescrape_file" >> "$BASE_DIR/logs/rescrape_${machine}.log" 2>&1 &
                log "  Started PID $!"
            else
                log "  Cannot restart rescrape — no place_ids file for $machine"
            fi
            ;;
        main)
            log "  Restarting: main scraper"
            cd "$SCRAPER_DIR"
            PYTHONPATH=src nohup "$PYTHON" -u -m gmaps_scraper --cuisine-expansion >> "$BASE_DIR/logs/scraper_main.log" 2>&1 &
            log "  Started PID $!"
            ;;
    esac
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
log "Watchdog started (auto-restart mode)"

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

        # Crash recovery: if a scraper was previously running, check if it has unfinished work
        if [ -f "$LAST_SCRAPER_FILE" ]; then
            last_type=$(cat "$LAST_SCRAPER_FILE")
            last_checkpoint=$(get_checkpoint "$last_type")
            if [ -n "$last_checkpoint" ] && [ -f "$last_checkpoint" ]; then
                # Check if checkpoint shows incomplete work
                has_pending=$($PYTHON -c "
import json
try:
    p = json.load(open('$last_checkpoint'))
    phase = p.get('phase', '')
    if phase == 'complete':
        print('no')
    elif phase == 'details' and p.get('pending_links', 0) > 0:
        print('yes')
    elif phase == 'search' and p.get('completed_searches_count', 0) < 105184:
        print('yes')
    else:
        print('no')
except: print('no')
" 2>/dev/null)
                if [ "$has_pending" = "yes" ]; then
                    log "CRASH DETECTED: $last_type exited with unfinished work — restarting"
                    send_telegram_alert "💥 WATCHDOG: $last_type crashed (process gone). Restarting from checkpoint."
                    sleep 5
                    restart_scraper "$last_type"
                    send_telegram_alert "✅ WATCHDOG: $last_type restarted from checkpoint."
                fi
            fi
        fi
        continue
    fi

    # Remember what's running so we can restart on crash
    echo "$scraper_type" > "$LAST_SCRAPER_FILE"

    checkpoint=$(get_checkpoint "$scraper_type")
    chrome=$(chrome_count)
    stale_secs=$(check_staleness "$checkpoint")

    # Chrome bloat check (>60 processes)
    if [ "$chrome" -gt 60 ]; then
        log "WARNING: $chrome Chrome processes (scraper=$scraper_type) — killing stale Chrome"
        pkill -9 -f "Google Chrome.*bota" 2>/dev/null || true
        sleep 2
    fi

    # fseventsd bloat check — heavy scraper I/O causes it to leak memory
    # It stores no useful data for us (just FS change notifications for Spotlight/Time Machine).
    # Safe to kill; launchd auto-restarts it fresh within seconds.
    fseventsd_rss=$(ps -p $(pgrep -x fseventsd 2>/dev/null || echo 0) -o rss= 2>/dev/null | tr -d ' ')
    if [ -n "$fseventsd_rss" ] && [ "$fseventsd_rss" -gt 2097152 ]; then
        fseventsd_mb=$((fseventsd_rss / 1024))
        log "WARNING: fseventsd using ${fseventsd_mb}MB RAM — killing (auto-restarts clean)"
        # To enable: echo "USERNAME ALL=(root) NOPASSWD: /usr/bin/killall fseventsd" | sudo tee /etc/sudoers.d/watchdog-fseventsd
        sudo -n /usr/bin/killall fseventsd 2>/dev/null
        if [ $? -eq 0 ]; then
            send_telegram_alert "🧹 WATCHDOG: Killed bloated fseventsd (${fseventsd_mb}MB). Auto-restarted."
        else
            log "  Cannot kill fseventsd — needs sudoers entry for passwordless killall fseventsd"
            send_telegram_alert "⚠️ WATCHDOG: fseventsd bloated (${fseventsd_mb}MB) but can't kill — needs sudoers"
        fi
    fi

    # Staleness check
    if [ -n "$stale_secs" ] && [ "$stale_secs" -gt "$STALE_SECONDS" ]; then
        stale_min=$((stale_secs / 60))
        log "STALE: $scraper_type no update in ${stale_min}m (chrome=$chrome) — killing and restarting"
        send_telegram_alert "⚠️ WATCHDOG: $scraper_type stalled (${stale_min}m). Killing and restarting."
        kill_all_scrapers
        sleep 5
        restart_scraper "$scraper_type"
        send_telegram_alert "✅ WATCHDOG: $scraper_type restarted from checkpoint."
    fi
done
