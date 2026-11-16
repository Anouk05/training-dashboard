"""Incremental Garmin Connect Personal API sync -> CSV files in ./data/garmin/.

Usage (from the project root):
    python -m sync garmin             # sync everything (incremental)
    python -m sync garmin activities  # only activities
    python -m sync garmin daily       # only daily wellness
    python -m sync garmin zones       # only heart rate zones
    python -m sync garmin weight      # only weight (Index scale)
    python -m sync garmin cycle       # only menstrual cycles
    python -m sync garmin load        # only rebuild training_load.csv (no API calls)

Outputs: activities.csv, daily.csv, training_load.csv, hr_zones.csv, weight.csv, cycle.csv.
Each run only fetches data newer than what is already in the CSVs, plus a small overlap because Garmin
finalizes sleep/HRV/load a little later. Stdlib only.
"""

from __future__ import annotations

from .activities import sync_activities
from .wellness import build_training_load, sync_cycle, sync_daily, sync_weight, sync_zones


def sync(what: str = "all") -> None:
    acts = daily = None
    if what in ("all", "activities"):
        acts = sync_activities()
    if what in ("all", "zones"):
        sync_zones()
    if what in ("all", "daily"):
        daily = sync_daily(acts)
    if what in ("all", "weight"):
        try:
            sync_weight()
        except Exception as e:
            print(f"weight: skipped ({e})")
    if what in ("all", "cycle"):
        try:
            sync_cycle()
        except Exception as e:  # cycle tracking is optional; never block the rest of the sync
            print(f"cycle: skipped ({e})")
    build_training_load(acts, daily)

