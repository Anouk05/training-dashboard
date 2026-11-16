"""Paths, the file cache and small helpers shared by every module (no data logic here)."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # the sync clients live in sync/ in the project root
    sys.path.insert(0, str(ROOT))


DATA = ROOT / "data"  # everything personal: synced data, plans, reports, food log (never in git)


GARMIN = DATA / "garmin"


DETAILS = GARMIN / "details"


PLANS = DATA / "plans"


LIBRARY = ROOT / "library" / "workouts.yaml"


RULES = ROOT / "coach" / "rules.yaml"


ICU = DATA / "intervals"


REPORTS = DATA / "reports" / "workouts"


# load per hour by intensity, calibrated on intervals.icu's load for your planned workouts (50′ Z2 run = 54, 30′ at threshold = 69)
LOAD_PER_HOUR = {"easy": 62, "moderate": 85, "hard": 130, "rest": 35}


SPORT_NAMES = {"run": "Run", "ride": "Ride", "swim": "Swim", "row": "Row", "str": "Strength", "other": "Other"}


ICU_SPORT = {"Run": "run", "TrailRun": "run", "VirtualRun": "run", "Ride": "ride", "VirtualRide": "ride", "GravelRide": "ride",
             "MountainBikeRide": "ride", "EBikeRide": "ride", "Swim": "swim", "OpenWaterSwim": "swim", "Rowing": "row",
             "VirtualRow": "row", "WeightTraining": "str"}


FEEL = {1: "Strong", 2: "Good", 3: "Normal", 4: "Poor", 5: "Weak"}  # intervals.icu feel scale


ICU_LOAD_FROM = date(2025, 3, 1)  # intervals.icu history (and its training load) starts here


def cached(path: Path, parse):
    """Re-parse a file only when its mtime changes."""
    mtime = path.stat().st_mtime if path.exists() else 0
    return _cached_inner(str(path), mtime, parse)


@lru_cache(maxsize=64)
def _cached_inner(path: str, mtime: float, parse):
    return parse(Path(path)) if mtime else None


def read_csv(p: Path):
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def read_json(p: Path):
    return json.loads(p.read_text())


def read_yaml(p: Path):
    return yaml.safe_load(p.read_text()) or {}


def num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def sport_of(t: str) -> str:
    t = t or ""
    if "running" in t:
        return "run"
    if "swimming" in t:
        return "swim"
    if "rowing" in t:
        return "row"
    if "cycling" in t or "biking" in t:
        return "ride"
    if "strength" in t:
        return "str"
    return "other"


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def fmt_dur(m: float) -> str:
    m = round(m)
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m}′"


def clean_name(n: str) -> str:
    return re.sub(r"^[A-Z][\w\-' ]+ - ", "", n or "").strip()


def athlete_name() -> str:
    """Your first name for the greeting, from ATHLETE_NAME in .env (kept out of git)."""
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.strip().startswith("ATHLETE_NAME="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return ""


def fmt_pace(p: float) -> str:
    m, s = int(p), round((p - int(p)) * 60)
    return f"{m + 1}:00" if s == 60 else f"{m}:{s:02d}"


def as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def fmt_hms(m: float) -> str:
    s = round(m * 60)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
