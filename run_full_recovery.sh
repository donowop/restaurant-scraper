#!/bin/bash
# Full recovery pipeline:
#   1. Pre-load cached links + Phase 1 re-search + Phase 2 scrape
#   2. Rescrape rejected place_ids
#
# Usage: ./run_full_recovery.sh m1   (or m2)

set -euo pipefail

MACHINE="${1:?Usage: $0 m1|m2}"
cd "$(dirname "$0")/us-restaurant-scraper"
PYTHON=".venv/bin/python3"
export PYTHONPATH=src

echo "=========================================="
echo "FULL RECOVERY PIPELINE — $MACHINE"
echo "Started: $(date)"
echo "=========================================="

# Clean up stale Chrome processes before starting
CHROME_COUNT=$(pgrep -f "Google Chrome.*bota" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
if [ "$CHROME_COUNT" -gt 0 ]; then
    echo "Cleaning up $CHROME_COUNT stale Chrome processes..."
    pkill -9 -f "Google Chrome.*bota" 2>/dev/null || true
    sleep 2
fi

# --- Step 1: Recovery (pre-load cached links → Phase 1 re-search → Phase 2 scrape) ---
LINKS_FILE="../${MACHINE}_recovery_links.json"
QUERY_FILE="../${MACHINE}_recovery_queries.json"

ARGS=""
if [ -f "$LINKS_FILE" ]; then
    ARGS="$ARGS --links-file $LINKS_FILE"
fi
if [ -f "$QUERY_FILE" ]; then
    ARGS="$ARGS --query-file $QUERY_FILE"
fi

if [ -n "$ARGS" ]; then
    echo ""
    echo ">>> STEP 1: Recovery (cached links + re-search + scrape)"
    echo ""
    $PYTHON -u ../recovery_search.py $ARGS
    echo ""
    echo ">>> STEP 1 COMPLETE: $(date)"
else
    echo ">>> STEP 1 SKIPPED: no links or query files found"
fi

# --- Step 2: Rescrape rejected place_ids ---
RESCRAPE_FILE="../${MACHINE}_rescrape_place_ids.json"
if [ -f "$RESCRAPE_FILE" ]; then
    echo ""
    echo ">>> STEP 2: Rescrape rejected place_ids"
    echo ""
    $PYTHON -u ../rescrape_rejected.py --place-ids-file "$RESCRAPE_FILE"
    echo ""
    echo ">>> STEP 2 COMPLETE: $(date)"
else
    echo ">>> STEP 2 SKIPPED: $RESCRAPE_FILE not found"
fi

echo ""
echo "=========================================="
echo "ALL STEPS COMPLETE — $MACHINE"
echo "Finished: $(date)"
echo "=========================================="
