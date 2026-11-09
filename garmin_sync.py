#!/usr/bin/env python3
"""Incremental Garmin Connect Personal API sync -> CSV files in ./garmin_data/.

Usage:
    python3 garmin_sync.py            # sync everything (incremental)
    python3 garmin_sync.py activities # only activities
    python3 garmin_sync.py daily      # only daily wellness
    python3 garmin_sync.py zones      # only heart rate zones
    python3 garmin_sync.py weight     # only weight (Index scale)
    python3 garmin_sync.py cycle      # only menstrual cycles
    python3 garmin_sync.py load       # only rebuild training_load.csv (no API calls)

Outputs: activities.csv, daily.csv, training_load.csv, hr_zones.csv, weight.csv, cycle.csv.
Each run only fetches data newer than what is already in the CSVs, plus a small overlap because Garmin
finalizes sleep/HRV/load a little later. Stdlib only. The code lives in the garmin/ package.
"""

from __future__ import annotations

import sys

from garmin.activities import sync_activities
from garmin.wellness import build_training_load, sync_cycle, sync_daily, sync_weight, sync_zones


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


if __name__ == "__main__":
    sync(sys.argv[1] if len(sys.argv) > 1 else "all")
