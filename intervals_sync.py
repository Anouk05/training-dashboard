#!/usr/bin/env python3
"""Incremental intervals.icu sync -> intervals_data/.

Usage:
    python3 intervals_sync.py

Outputs (in ./intervals_data/):
    activities.csv   one row per activity: intervals load, RPE, feel, your notes, link to the Garmin id
    wellness.csv     one row per day: fitness (CTL), fatigue (ATL), ramp rate, subjective scores
    events.json      the calendar: planned workouts, notes, races, season starts (fully refreshed each run)

Needs INTERVALS_API_KEY and INTERVALS_ATHLETE_ID in .env. Stdlib only.
"""

from __future__ import annotations

import base64
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "intervals_data"
BASE_URL = "https://intervals.icu/api/v1"
ACTIVITIES_CSV = DATA_DIR / "activities.csv"
WELLNESS_CSV = DATA_DIR / "wellness.csv"
EVENTS_JSON = DATA_DIR / "events.json"
SETTINGS_JSON = DATA_DIR / "settings.json"

OVERLAP_DAYS = 3          # re-fetch recent days: RPE, notes and load get edited after the fact
HISTORY_START = "2015-01-01"
EVENTS_FROM = "2024-01-01"  # calendar window: from here …
EVENTS_AHEAD_DAYS = 400     # … to this far ahead


def _env() -> tuple[str, str]:
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    key = os.environ.get("INTERVALS_API_KEY") or vals.get("INTERVALS_API_KEY")
    aid = os.environ.get("INTERVALS_ATHLETE_ID") or vals.get("INTERVALS_ATHLETE_ID")
    if not key or not aid:
        sys.exit("INTERVALS_API_KEY / INTERVALS_ATHLETE_ID not found in .env")
    return key, aid


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


def request(method: str, path: str, body: dict | None = None):
    key, aid = _env()
    url = BASE_URL + path.replace("{athlete}", aid)
    headers = {
        "Authorization": "Basic " + base64.b64encode(f"API_KEY:{key}".encode()).decode(),
        "Accept": "application/json",
        # intervals.icu sits behind Cloudflare, which blocks the default Python user agent
        "User-Agent": "training-dashboard/1.0",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read()[:300]!r}") from None
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if attempt >= 3:
                raise
            print(f"  network error ({e}), retrying", flush=True)
            time.sleep(5)


def get(path: str):
    return request("GET", path)


# --------------------------------------------------------------------------- csv helpers

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def _since(rows: list[dict], key: str) -> str:
    if not rows:
        return HISTORY_START
    return (date.fromisoformat(max(r[key] for r in rows)[:10]) - timedelta(days=OVERLAP_DAYS)).isoformat()


def _r(v, nd=1):
    return round(v, nd) if isinstance(v, (int, float)) else v


# --------------------------------------------------------------------------- activities

ACTIVITY_COLUMNS = [
    "icu_id", "garmin_id", "date", "start_local", "type", "name", "load", "rpe", "feel", "notes",
    "moving_min", "distance_km", "avg_hr", "decoupling", "efficiency_factor", "compliance", "paired_event_id",
    "ftp", "avg_watts", "np", "hr_zone_times", "power_zone_times",
]


def sync_activities() -> list[dict]:
    rows_ = read_csv(ACTIVITIES_CSV)
    # a column was added since the last run: fetch everything once so old rows get it too
    existing = {r["icu_id"]: r for r in rows_} if rows_ and set(ACTIVITY_COLUMNS) <= set(rows_[0]) else {}
    since = _since(list(existing.values()), "date")
    rows = get(f"/athlete/{{athlete}}/activities?oldest={since}&newest={(date.today() + timedelta(days=1)).isoformat()}") or []
    for a in rows:
        existing[a["id"]] = _activity_row(a)
    out = sorted(existing.values(), key=lambda r: r["start_local"])
    write_csv(ACTIVITIES_CSV, out, ACTIVITY_COLUMNS)
    print(f"intervals activities: {len(rows)} fetched since {since}, {len(out)} total")
    return out


# --------------------------------------------------------------------------- wellness

WELLNESS_COLUMNS = ["date", "ctl", "atl", "ramp_rate", "hrv", "resting_hr", "sleep_score", "readiness",
                    "soreness", "fatigue", "stress", "mood", "motivation", "injury", "comments"]


def sync_wellness() -> list[dict]:
    existing = {r["date"]: r for r in read_csv(WELLNESS_CSV)}
    since = _since(list(existing.values()), "date")
    rows = get(f"/athlete/{{athlete}}/wellness?oldest={since}&newest={date.today().isoformat()}") or []
    for w in rows:
        existing[w["id"]] = {
            "date": w["id"], "ctl": _r(w.get("ctl")), "atl": _r(w.get("atl")), "ramp_rate": _r(w.get("rampRate"), 2),
            "hrv": w.get("hrv"), "resting_hr": w.get("restingHR"), "sleep_score": w.get("sleepScore"),
            "readiness": w.get("readiness"), "soreness": w.get("soreness"), "fatigue": w.get("fatigue"),
            "stress": w.get("stress"), "mood": w.get("mood"), "motivation": w.get("motivation"),
            "injury": w.get("injury"), "comments": (w.get("comments") or "").strip(),
        }
    out = sorted(existing.values(), key=lambda r: r["date"])
    write_csv(WELLNESS_CSV, out, WELLNESS_COLUMNS)
    print(f"intervals wellness: {len(rows)} days fetched since {since}, {len(out)} total")
    return out


# --------------------------------------------------------------------------- calendar

EVENT_KEYS = ["id", "start_date_local", "end_date_local", "category", "name", "type", "description", "moving_time",
              "distance", "icu_training_load", "for_week", "paired_activity_id", "color"]


def sync_events() -> list[dict]:
    t = date.today()
    oldest, newest = date.fromisoformat(EVENTS_FROM), t + timedelta(days=EVENTS_AHEAD_DAYS)
    rows = get(f"/athlete/{{athlete}}/events?oldest={oldest}&newest={newest}") or []
    out = [{k: e.get(k) for k in EVENT_KEYS} for e in rows]
    DATA_DIR.mkdir(exist_ok=True)
    EVENTS_JSON.write_text(json.dumps({"synced": t.isoformat(), "oldest": oldest.isoformat(), "events": out}, indent=1))
    print(f"intervals calendar: {len(out)} events ({oldest} .. {newest})")
    return out


def move_event(event_id: int, to: date, time: str = "00:00:00") -> dict:
    """Move a planned workout to another day, or set its time of day (it follows to the watch via intervals.icu)."""
    return request("PUT", f"/athlete/{{athlete}}/events/{event_id}", {"start_date_local": f"{to.isoformat()}T{time}"})


EDITABLE = ("name", "description", "type", "start_date_local")


def update_event(event_id: int, changes: dict) -> dict:
    """Change a planned workout (name, steps, sport or date). intervals.icu re-reads the steps,
    recomputes duration and load, and syncs the change to the watch."""
    body = {k: v for k, v in changes.items() if k in EDITABLE}
    if not body:
        raise ValueError("nothing to change")
    return request("PUT", f"/athlete/{{athlete}}/events/{event_id}", body)


def create_event(day: date, name: str, sport_type: str, description: str) -> dict:
    """Add a planned workout to the calendar (intervals.icu sends it to the watch)."""
    return request("POST", "/athlete/{athlete}/events", {
        "category": "WORKOUT", "start_date_local": f"{day.isoformat()}T00:00:00",
        "name": name, "type": sport_type, "description": description,
    })


def create_week_note(monday: date, name: str, description: str = "", color: str = "#666666") -> dict:
    """Add a weekly note (shown above the week in intervals.icu; the dashboard reads it as the phase label)."""
    return request("POST", "/athlete/{athlete}/events", {
        "category": "NOTE", "start_date_local": f"{monday.isoformat()}T00:00:00",
        "end_date_local": f"{(monday + timedelta(days=1)).isoformat()}T00:00:00",
        "name": name, "description": description, "for_week": True, "color": color,
    })


def update_week_note(event_id: int, name: str, description: str, color: str) -> dict:
    return request("PUT", f"/athlete/{{athlete}}/events/{event_id}", {"name": name, "description": description, "color": color})


def delete_event(event_id: int) -> None:
    """Remove a planned workout from the calendar (and from the watch)."""
    request("DELETE", f"/athlete/{{athlete}}/events/{event_id}")


def sync_settings() -> list[dict]:
    """Heart-rate and power zones per sport, as set in intervals.icu (the dashboard's reference zones)."""
    keys = ["types", "lthr", "max_hr", "hr_zones", "hr_zone_names", "ftp", "power_zones", "power_zone_names"]
    out = [{k: s.get(k) for k in keys} for s in (get("/athlete/{athlete}") or {}).get("sportSettings", [])]
    DATA_DIR.mkdir(exist_ok=True)
    SETTINGS_JSON.write_text(json.dumps(out, indent=1))
    print(f"intervals settings: zones for {len(out)} sport groups")
    return out


def _activity_row(a: dict) -> dict:
    return {
        "icu_id": a["id"], "garmin_id": a.get("external_id") if a.get("source") == "GARMIN_CONNECT" else "",
        "date": a["start_date_local"][:10], "start_local": a["start_date_local"], "type": a.get("type"),
        "name": a.get("name"), "load": a.get("icu_training_load"), "rpe": a.get("icu_rpe"), "feel": a.get("feel"),
        "notes": (a.get("description") or "").strip(), "moving_min": _r((a.get("moving_time") or 0) / 60),
        "distance_km": _r((a.get("distance") or 0) / 1000, 2), "avg_hr": a.get("average_heartrate"),
        "decoupling": _r(a.get("decoupling")), "efficiency_factor": _r(a.get("icu_efficiency_factor"), 3),
        "compliance": _r(a.get("compliance")), "paired_event_id": a.get("paired_event_id"),
        "ftp": a.get("icu_ftp"), "avg_watts": a.get("icu_average_watts"), "np": a.get("icu_weighted_avg_watts"),
        # seconds per HR zone, as intervals.icu computed them with the zones set at the time
        "hr_zone_times": json.dumps(a["icu_hr_zone_times"]) if a.get("icu_hr_zone_times") else "",
        # seconds per power zone Z1–Z7 (the overlapping sweet-spot band is left out)
        "power_zone_times": json.dumps([z["secs"] for z in a["icu_zone_times"] if z.get("id", "").startswith("Z")])
        if a.get("icu_zone_times") else "",
    }


INTERVALS_DIR = DATA_DIR / "intervals"


def activity_sections(icu_id: str, refresh: bool = False) -> list[dict]:
    """The workout's sections (warm-up, efforts, recoveries) as intervals.icu split them, cached per activity.
    Work sections of 20 minutes or more also get the last 20 minutes' average HR and power, the numbers a
    30-minute threshold test is read from."""
    INTERVALS_DIR.mkdir(parents=True, exist_ok=True)
    f = INTERVALS_DIR / f"{icu_id}.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    raw = (get(f"/activity/{icu_id}/intervals") or {}).get("icu_intervals") or []
    out = [{
        "type": x.get("type"), "label": x.get("label"),
        "start": x.get("start_time"), "end": x.get("end_time"), "moving_s": x.get("moving_time"),
        "avg_watts": x.get("average_watts"), "np": x.get("weighted_average_watts"), "max_watts": x.get("max_watts"),
        "avg_hr": x.get("average_heartrate"), "max_hr": x.get("max_heartrate"), "cadence": _r(x.get("average_cadence"), 0),
        "intensity": x.get("intensity"), "zone": x.get("zone"), "distance_m": x.get("distance"),
        "speed": x.get("average_speed"), "decoupling": _r(x.get("decoupling")),
    } for x in raw]
    long_work = [x for x in out if x["type"] == "WORK" and (x["end"] - x["start"]) >= 1200]
    if long_work:
        streams = {s["type"]: s.get("data") or [] for s in get(f"/activity/{icu_id}/streams?types=time,heartrate,watts") or []}
        t, hr, w = streams.get("time", []), streams.get("heartrate", []), streams.get("watts", [])
        for x in long_work:
            idx = [i for i, ti in enumerate(t) if x["end"] - 1200 <= ti < x["end"]]
            hrs = [hr[i] for i in idx if i < len(hr) and hr[i]]
            ws = [w[i] for i in idx if i < len(w) and w[i] is not None]
            x["last20_hr"] = round(sum(hrs) / len(hrs), 1) if hrs else None
            x["last20_watts"] = round(sum(ws) / len(ws)) if ws else None
    f.write_text(json.dumps(out))
    return out


def set_activity_notes(icu_id: str, notes: str) -> dict:
    """Save your notes on a completed workout (the activity description in intervals.icu), then refresh its row.
    The current name is sent along: on its own, a description update makes intervals.icu reset the name."""
    current = get(f"/activity/{icu_id}")
    request("PUT", f"/activity/{icu_id}", {"description": notes, "name": current.get("name")})
    fresh = get(f"/activity/{icu_id}")
    if fresh.get("name") != current.get("name"):  # belt and braces
        request("PUT", f"/activity/{icu_id}", {"name": current.get("name")})
        fresh = get(f"/activity/{icu_id}")
    rows = {r["icu_id"]: r for r in read_csv(ACTIVITIES_CSV)}
    rows[icu_id] = _activity_row(fresh)
    write_csv(ACTIVITIES_CSV, sorted(rows.values(), key=lambda r: r["start_local"]), ACTIVITY_COLUMNS)
    return rows[icu_id]


def sync() -> None:
    sync_settings()
    sync_activities()
    sync_wellness()
    sync_events()


if __name__ == "__main__":
    sync()
