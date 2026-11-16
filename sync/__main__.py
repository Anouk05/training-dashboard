"""Run a sync from the project root, the same one as the dashboard's Sync button.

    python -m sync                  # everything: Garmin, intervals.icu, Notion (+ planned gym sessions)
    python -m sync garmin [what]    # only Garmin; what = activities, daily, zones, weight, cycle or load
    python -m sync intervals        # only intervals.icu
    python -m sync notion [plan|setup]
"""

from __future__ import annotations

import sys

from . import garmin, intervals, notion


def push_gym_plan() -> None:
    from app.backend.strength import notion_plan  # the targets come from the dashboard's strength module
    notion.push_plan(notion_plan())


def sync_all() -> None:
    garmin.sync()
    intervals.sync()
    try:  # Notion is optional and never blocks the rest
        notion.sync()
        push_gym_plan()
    except Exception as e:
        print(f"notion: skipped ({e})")


def main(args: list[str]) -> None:
    src, rest = (args[0], args[1:]) if args else ("all", [])
    if src == "all":
        sync_all()
    elif src == "garmin":
        garmin.sync(rest[0] if rest else "all")
    elif src == "intervals":
        intervals.sync()
    elif src == "notion":
        cmd = rest[0] if rest else "sync"
        push_gym_plan() if cmd == "plan" else notion.setup_sessions() if cmd == "setup" else notion.sync()
    else:
        sys.exit(__doc__)


main(sys.argv[1:])
