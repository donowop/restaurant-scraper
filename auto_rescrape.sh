#!/bin/bash
# Auto-rescrape rejected places after detail phase finishes.
# Starts immediately and waits for the main scraper to complete.
#
# Usage:
#   nohup ./auto_rescrape.sh > rescrape_output.log 2>&1 &
#
# The Python script handles waiting, checkpointing, and CA-first ordering.

set -euo pipefail

cd "$(dirname "$0")"

echo "[$(date)] auto_rescrape.sh started"
echo "[$(date)] Rescraping rejected/failed places..."

PYTHONPATH=us-restaurant-scraper/src us-restaurant-scraper/.venv/bin/python -u rescrape_rejected.py "$@" 2>&1

echo "[$(date)] auto_rescrape.sh finished"
