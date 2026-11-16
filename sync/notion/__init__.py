"""Strength training in Notion -> data/notion/strength.csv.

Each planned gym session is a page in the "Gym sessions" database (show it as a calendar) with a checklist of your
exercises and their proposed sets × reps @ load. Tick what you did; type changes at the end of a line. Older sessions
logged row by row in the "Strength log" database are read too. The dashboard's Sync button runs all of this.

Usage (from the project root):
    python -m sync notion            # read your logged sessions into data/notion/strength.csv
    python -m sync notion plan       # put planned gym sessions (with proposed sets, reps, load) in Notion
    python -m sync notion setup      # create the databases on NOTION_PAGE_ID (once)

Needs NOTION_TOKEN (internal integration secret) and NOTION_PAGE_ID in .env; the page must be shared with the
integration (page ⋯ → Connections). Database ids are kept in data/notion/config.json.
"""

from __future__ import annotations

import csv

from .client import config, DATA_DIR, ROOT
from .log import ROUTINE, read_log
from .sessions import push_plan, read_checklists, setup_sessions

STRENGTH_CSV = DATA_DIR / "strength.csv"
COLUMNS = ["date", "exercise", "sets", "reps", "kg", "rpe", "note", "page_id", "edited", "source"]

__all__ = ["sync", "push_plan", "ROUTINE"]


def sync() -> list[dict]:
    """Logged sets from the session checklists and the Strength log; for the same day and exercise the log row wins."""
    if not config().get("database_id"):
        print("notion: not set up yet (run: python -m sync notion setup)")
        return []
    rows = {(r["date"], r["exercise"].lower()): r for r in read_checklists()}
    rows.update({(r["date"], r["exercise"].lower()): r for r in read_log()})
    out = sorted(rows.values(), key=lambda r: (r["date"], r["exercise"]))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STRENGTH_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(out)
    print(f"notion: {len(out)} strength rows -> {STRENGTH_CSV.relative_to(ROOT)}")
    return out

