from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

from takopi.api import CommandContext, CommandResult

BASE_DIR = "/Users/donosclawdbot/repos/restaurant-scraper"
SCRAPER_DIR = os.path.join(BASE_DIR, "us-restaurant-scraper")
MAIN_CHECKPOINT_DIR = os.path.join(SCRAPER_DIR, "checkpoints")
RECOVERY_CHECKPOINT_DIR = os.path.join(SCRAPER_DIR, "checkpoints_recovery")
STALE_THRESHOLD_MINUTES = 30


def _find_running_scraper() -> str | None:
    """Detect which scraper process is running."""
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        lines = result.stdout
        if "recovery_search" in lines or "run_full_recovery" in lines:
            return "recovery"
        if "rescrape_rejected" in lines:
            return "rescrape"
        if "gmaps_scraper" in lines and "grep" not in lines:
            return "main"
    except Exception:
        pass
    return None


def _chrome_count() -> int:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "Google Chrome.*bota"],
            capture_output=True, text=True, timeout=5,
        )
        return len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception:
        return 0


def _get_run_status(last_update: str, scraper_type: str | None) -> str:
    if not scraper_type:
        return "Stopped"
    if not last_update:
        return "Running"
    try:
        last = datetime.fromisoformat(last_update)
        minutes_since = (datetime.now() - last).total_seconds() / 60
        if minutes_since > STALE_THRESHOLD_MINUTES:
            return f"STALLED ({minutes_since:.0f}m ago)"
    except Exception:
        pass
    return "Running"


def _read_json(path: str) -> dict | list | None:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _recovery_status() -> str:
    """Status for recovery_search.py (Phase 1 + Phase 2)."""
    progress = _read_json(os.path.join(RECOVERY_CHECKPOINT_DIR, "progress.json"))
    if not progress:
        return "Recovery: no checkpoint found"

    phase = progress.get("phase", "unknown")
    last_update = progress.get("last_update", "")
    scraper_type = _find_running_scraper()
    status = _get_run_status(last_update, scraper_type)
    chrome = _chrome_count()
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")

    lines = [
        "```",
        f"RECOVERY STATUS ({time_str})",
        f"{'═' * 40}",
        f"Status:      {status}",
        f"Chrome:      {chrome} processes",
        f"{'─' * 40}",
    ]

    if phase == "search":
        done = progress.get("completed_searches", 0)
        total = progress.get("total_queries", 0)
        pending = progress.get("pending_links", 0)
        new_links = progress.get("total_new_links", 0)
        pct = done / total * 100 if total else 0

        lines.extend([
            f"Phase:       1 (Re-search)",
            f"Searches:    {done:,} / {total:,} ({pct:.1f}%)",
            f"Pending:     {pending:,} links",
            f"  Cached:    {pending - new_links:,}",
            f"  New:       {new_links:,}",
        ])

    elif phase == "details":
        done = progress.get("completed_details", 0)
        pending = progress.get("pending_links", 0)
        saved = progress.get("total_restaurants_saved", 0)
        total = done + pending
        pct = done / total * 100 if total else 0

        lines.extend([
            f"Phase:       2 (Detail scrape)",
            f"Details:     {done:,} / {total:,} ({pct:.1f}%)",
            f"Saved:       {saved:,} restaurants",
            f"Pending:     {pending:,} links",
        ])

    lines.extend([f"{'═' * 40}", "```"])
    return "\n".join(lines)


def _rescrape_status() -> str:
    """Status for rescrape_rejected.py."""
    done_data = _read_json(os.path.join(MAIN_CHECKPOINT_DIR, "rescrape_done.json"))
    done_count = len(done_data) if isinstance(done_data, list) else 0

    # Check for place_ids files to get total
    total = 0
    for name in ["m1_rescrape_place_ids.json", "m2_rescrape_place_ids.json"]:
        data = _read_json(os.path.join(BASE_DIR, name))
        if isinstance(data, list):
            total = max(total, len(data))

    scraper_type = _find_running_scraper()
    status = "Running" if scraper_type == "rescrape" else "Stopped"
    chrome = _chrome_count()
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    pct = done_count / total * 100 if total else 0

    lines = [
        "```",
        f"RESCRAPE STATUS ({time_str})",
        f"{'═' * 40}",
        f"Status:      {status}",
        f"Chrome:      {chrome} processes",
        f"{'─' * 40}",
        f"Done:        {done_count:,} / {total:,} ({pct:.1f}%)",
        f"{'═' * 40}",
        "```",
    ]
    return "\n".join(lines)


def _main_status() -> str:
    """Status for the main gmaps_scraper."""
    progress = _read_json(os.path.join(MAIN_CHECKPOINT_DIR, "progress.json"))
    if not progress:
        return "Main scraper: no checkpoint found"

    phase = progress.get("phase", "search")
    completed_searches = progress.get("completed_searches_count", 0)
    completed_details = progress.get("completed_details", 0)
    saved = progress.get("total_restaurants_saved", 0)
    last_update = progress.get("last_update", "")

    scraper_type = _find_running_scraper()
    status = _get_run_status(last_update, scraper_type)
    chrome = _chrome_count()
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")

    lines = [
        "```",
        f"SCRAPER STATUS ({time_str})",
        f"{'═' * 40}",
        f"Status:      {status}",
        f"Chrome:      {chrome} processes",
        f"{'─' * 40}",
        f"Phase:       {phase}",
        f"Searches:    {completed_searches:,}",
        f"Details:     {completed_details:,}",
        f"Saved:       {saved:,} restaurants",
        f"{'═' * 40}",
        "```",
    ]
    return "\n".join(lines)


def _get_status() -> str:
    """Auto-detect running scraper and show appropriate status."""
    scraper_type = _find_running_scraper()

    if scraper_type == "recovery":
        return _recovery_status()
    elif scraper_type == "rescrape":
        return _rescrape_status()
    elif scraper_type == "main":
        return _main_status()
    else:
        # Nothing running — show most recent checkpoint
        recovery_prog = _read_json(os.path.join(RECOVERY_CHECKPOINT_DIR, "progress.json"))
        main_prog = _read_json(os.path.join(MAIN_CHECKPOINT_DIR, "progress.json"))

        # Show recovery if it exists, otherwise main
        if recovery_prog:
            return _recovery_status()
        elif main_prog:
            return _main_status()
        else:
            return "```\nNo scraper data found.\n```"


class ScraperStatusCommand:
    id = "scraper_status"
    description = "check scraper progress"

    async def handle(self, ctx: CommandContext) -> CommandResult | None:
        return CommandResult(text=_get_status())


BACKEND = ScraperStatusCommand()
