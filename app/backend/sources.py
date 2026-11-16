"""Read the synced data: activities (Garmin + intervals.icu, de-duplicated), wellness, the calendar, zones,
the workout library, coach rules and menstrual cycles. Everything else builds on these readers."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from .store import cached, FEEL, GARMIN, ICU, ICU_SPORT, LIBRARY, num, read_csv, read_json, read_yaml, REPORTS, RULES, sport_of


def activities() -> tuple[list[dict], int, float]:
    """(activities oldest first, duplicates removed and intervals.icu data merged in, #dropped, hours dropped)."""
    files = (GARMIN / "activities.csv", ICU / "activities.csv")
    return _merged(tuple(f.stat().st_mtime if f.exists() else 0 for f in files))


@lru_cache(maxsize=4)
def _merged(_mtimes):
    garmin, n, h = cached(GARMIN / "activities.csv", _parse_activities) or ([], 0, 0.0)
    icu_rows = icu_activities()
    by_garmin = {r["garmin_id"]: r for r in icu_rows if r["garmin_id"]}
    out = []
    for g in garmin:
        a = dict(g)  # never mutate the cached Garmin rows
        r = by_garmin.get(a["activity_id"])
        if r:
            _apply_icu(a, r)
        out.append(a)
    # activities that only exist in intervals.icu (uploads), unless they overlap a Garmin recording
    for r in icu_rows:
        if r["garmin_id"]:
            continue
        a = _icu_only(r)
        if not any(x["sport"] == a["sport"] and x["start"] < a["end"] and a["start"] < x["end"] for x in garmin):
            out.append(a)
    out.sort(key=lambda a: a["start"])
    return out, n, h


def _apply_icu(a: dict, r: dict) -> None:
    if num(r["load"]) is not None:
        a["load"] = num(r["load"])  # intervals.icu load: one consistent scale, also used for planned workouts
    if num(r["rpe"]):
        a["rpe"] = r["rpe"]
    a["feel_label"] = FEEL.get(int(num(r["feel"]))) if num(r["feel"]) else None
    a["notes"] = r["notes"]
    a["icu_id"] = r["icu_id"]
    a["paired_event_id"] = r["paired_event_id"]
    a["compliance"] = num(r["compliance"])
    a["decoupling"] = num(r["decoupling"])
    a["ftp"] = num(r.get("ftp"))
    a["np"] = num(r.get("np"))
    if r.get("hr_zone_times"):  # intervals.icu's own 7-zone split replaces Garmin's 5 zones
        a["zones"] = [x / 60 for x in json.loads(r["hr_zone_times"])]
    if not any(a["zones"]) and r.get("power_zone_times"):
        # no heart rate: fall back to power zones (heart rate stays first; running power is unreliable)
        a["zones"] = [x / 60 for x in json.loads(r["power_zone_times"])]
        a["zone_source"] = "power"


def _icu_only(r: dict) -> dict:
    start = datetime.fromisoformat(r["start_local"])
    minutes, km = num(r["moving_min"]) or 0, num(r["distance_km"]) or 0
    sport = ICU_SPORT.get(r["type"], "other")
    a = {"activity_id": r["icu_id"], "date": r["date"], "start_local": r["start_local"].replace("T", " "), "name": r["name"],
         "type": r["type"], "sport": sport, "start": start, "minutes": minutes, "end": start + timedelta(minutes=minutes),
         "load": num(r["load"]) or 0, "km": km, "zones": [0] * 5, "avg_hr": r["avg_hr"], "max_hr": "",
         "pace_min_per_km": round(minutes / km, 2) if sport == "run" and km else "", "avg_power": "", "rpe": r["rpe"],
         "feel": "", "te_label": ""}
    _apply_icu(a, r)
    return a


def analyses() -> dict[str, dict]:
    """Coach reports written by the analyze-workout skill, keyed by activity id."""
    if not REPORTS.exists():
        return {}
    key = tuple(sorted((f.name, f.stat().st_mtime) for f in REPORTS.glob("*.md")))
    return _analyses(key)


@lru_cache(maxsize=2)
def _analyses(key) -> dict[str, dict]:
    out = {}
    for name, _ in key:
        text = (REPORTS / name).read_text()
        meta, body = {}, text
        if text.startswith("---"):
            _, fm, body = text.split("---", 2)
            meta = yaml.safe_load(fm) or {}
        aid = str(meta.get("activity_id") or name.rsplit("-", 1)[-1].removesuffix(".md"))
        out[aid] = {"title": meta.get("title", ""), "rating": meta.get("rating"), "flags": meta.get("flags") or [],
                    "result": meta.get("result"), "body": body.strip(), "file": f"data/reports/workouts/{name}"}
    return out


def icu_activities() -> list[dict]:
    return cached(ICU / "activities.csv", read_csv) or []


def icu_wellness() -> dict[str, dict]:
    return {r["date"]: r for r in (cached(ICU / "wellness.csv", read_csv) or [])}


def events() -> list[dict]:
    """intervals.icu calendar: planned workouts, notes, races and season starts."""
    return (cached(ICU / "events.json", read_json) or {}).get("events", [])


def has_calendar() -> bool:
    return (ICU / "events.json").exists()


def ev_date(e: dict) -> date:
    return date.fromisoformat(e["start_date_local"][:10])


def _parse_activities(p: Path):
    rows = read_csv(p)
    acts = []
    for r in rows:
        a = dict(r)
        a["sport"] = sport_of(r["type"])
        a["start"] = datetime.fromisoformat(r["start_local"])
        a["minutes"] = num(r["duration_min"]) or 0
        a["end"] = a["start"] + timedelta(minutes=a["minutes"])
        a["load"] = num(r["training_load"]) or 0
        a["km"] = num(r["distance_km"]) or 0
        a["zones"] = [num(r[f"hr_z{z}_min"]) or 0 for z in range(1, 6)]
        acts.append(a)
    acts.sort(key=lambda a: a["start"])
    drop = set()
    for i, a in enumerate(acts):
        for b in acts[i + 1:i + 6]:
            if b["start"] > a["end"]:
                break
            if a["sport"] != b["sport"]:
                continue
            overlap = (min(a["end"], b["end"]) - max(a["start"], b["start"])).total_seconds() / 60
            if overlap > 0.5 * min(a["minutes"], b["minutes"]):
                # keep the copy with heart rate, then the one with more load
                ka = (1 if a["avg_hr"] else 0, a["load"])
                kb = (1 if b["avg_hr"] else 0, b["load"])
                drop.add(b["activity_id"] if ka >= kb else a["activity_id"])
    out = [a for a in acts if a["activity_id"] not in drop]
    return out, len(drop), round(sum(a["minutes"] for a in acts if a["activity_id"] in drop) / 60, 1)


def acts() -> list[dict]:
    return activities()[0]


def duplicate_stats() -> dict:
    _, n, h = activities()
    return {"count": n, "hours": h}


def daily() -> dict[str, dict]:
    rows = cached(GARMIN / "daily.csv", read_csv) or []
    return {r["date"]: r for r in rows}


def hr_zones() -> list[dict]:
    return cached(GARMIN / "hr_zones.csv", read_csv) or []


def latest_zones(sport: str) -> dict | None:
    rows = [r for r in hr_zones() if r["sport"] == sport]
    return rows[-1] if rows else None


ICU_TYPES = {"run": "Run", "ride": "Ride", "swim": "Swim"}


def zones_for(sport: str) -> dict | None:
    """Heart-rate zones for a sport: intervals.icu's settings (the reference), else Garmin's."""
    want = ICU_TYPES.get(sport, "Other")
    for st in cached(ICU / "settings.json", read_json) or []:
        if want in (st.get("types") or []) and st.get("hr_zones"):
            tops = st["hr_zones"]
            return {"source": "intervals.icu", "sport": want, "method": "LACTATE_THRESHOLD", "lthr": st.get("lthr"),
                    "max_hr": st.get("max_hr"), "floors": [0] + [t + 1 for t in tops[:-1]], "names": st.get("hr_zone_names")}
    zr = latest_zones({"run": "RUNNING", "ride": "CYCLING"}.get(sport, "DEFAULT")) or latest_zones("DEFAULT")
    return zr and {"source": "Garmin", "sport": zr["sport"], "method": zr["method"], "lthr": num(zr["lthr"]),
                   "max_hr": num(zr["max_hr"]), "floors": [num(zr[f"z{i}_floor"]) for i in range(1, 6)], "names": None}


def power_zones_for(sport: str, ftp: float | None) -> dict | None:
    """Power zones from intervals.icu (% of FTP), falling back to Coggan's levels."""
    if not ftp:
        return None
    want = ICU_TYPES.get(sport, "Other")
    st = next((x for x in cached(ICU / "settings.json", read_json) or [] if want in (x.get("types") or [])), {})
    pct = st.get("power_zones") or [55, 75, 90, 105, 120, 150, 999]
    return {"ftp": ftp, "floors": [0] + [round(ftp * p / 100) + 1 for p in pct[:-1]], "names": st.get("power_zone_names")}


def library() -> dict[str, dict]:
    data = cached(LIBRARY, read_yaml) or {}
    return {w["id"]: w for w in data.get("workouts", [])}


def rules() -> dict:
    return (cached(RULES, read_yaml) or {}).get("rules", {})


def cycles() -> list[dict]:
    return cached(GARMIN / "cycle.csv", read_csv) or []


def ftp_for(sport_type: str) -> float | None:
    for st in cached(ICU / "settings.json", read_json) or []:
        if sport_type in (st.get("types") or []):
            return num(st.get("ftp"))
    return None


def calendar(d0: date, d1: date, cats: tuple[str, ...]) -> list[dict]:
    return [e for e in events() if e["category"] in cats and d0 <= ev_date(e) <= d1]


RACE_CATS = ("RACE_A", "RACE_B", "RACE_C")


def settings_for(sport_type: str) -> dict:
    for st in cached(ICU / "settings.json", read_json) or []:
        if sport_type in (st.get("types") or []):
            return st
    return {}
