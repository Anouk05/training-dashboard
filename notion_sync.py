#!/usr/bin/env python3
"""Strength training in Notion -> notion_data/strength.csv.

Each planned gym session is a page in the "Gym sessions" database (show it as a calendar) with a checklist of your
exercises and their proposed sets × reps @ load. Tick what you did; type changes at the end of a line. Older sessions
logged row by row in the "Strength log" database are read too. The dashboard's Sync button runs all of this.

Usage:
    python3 notion_sync.py           # read your logged sessions into notion_data/strength.csv
    python3 notion_sync.py plan      # put planned gym sessions (with proposed sets, reps, load) in Notion
    python3 notion_sync.py setup     # create the databases on NOTION_PAGE_ID (once)

Needs NOTION_TOKEN (internal integration secret) and NOTION_PAGE_ID in .env; the page must be shared with the
integration (page ⋯ → Connections). Database ids are kept in notion_data/config.json. The code is in notion/.
"""

from __future__ import annotations

import csv
import sys

from notion.client import config, DATA_DIR, ROOT
from notion.log import ROUTINE, read_log
from notion.sessions import push_plan, read_checklists, setup_sessions

STRENGTH_CSV = DATA_DIR / "strength.csv"
COLUMNS = ["date", "exercise", "sets", "reps", "kg", "rpe", "note", "page_id", "edited", "source"]

__all__ = ["sync", "push_plan", "ROUTINE"]


def sync() -> list[dict]:
    """Logged sets from the session checklists and the Strength log; for the same day and exercise the log row wins."""
    if not config().get("database_id"):
        print("notion: not set up yet (run: python3 notion_sync.py setup)")
        return []
    rows = {(r["date"], r["exercise"].lower()): r for r in read_checklists()}
    rows.update({(r["date"], r["exercise"].lower()): r for r in read_log()})
    out = sorted(rows.values(), key=lambda r: (r["date"], r["exercise"]))
    DATA_DIR.mkdir(exist_ok=True)
    with STRENGTH_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"notion: {len(out)} strength rows -> {STRENGTH_CSV.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if cmd == "plan":  # the targets come from the dashboard's strength module
        from app.backend.strength import notion_plan
        push_plan(notion_plan())
    elif cmd == "setup":
        setup_sessions()
    else:
        sync()
