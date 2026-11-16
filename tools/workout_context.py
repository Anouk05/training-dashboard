#!/usr/bin/env python3
"""Gather everything needed to analyse one completed workout, as compact JSON.

Usage (from the Sport folder):
    .venv/bin/python tools/workout_context.py --pending        # completed workouts of the last 7 days without a report
    .venv/bin/python tools/workout_context.py latest           # context for the most recent workout
    .venv/bin/python tools/workout_context.py 12345678901      # context for one activity id

Used by the analyze-workout skill; reports are written to reports/workouts/<date>-<id>.md.
"""

from __future__ import annotations

import json
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.backend import activity, body, sources, store, week, workouts  # noqa: E402

REPORTS = ROOT / "reports" / "workouts"


def report_path(a: dict) -> Path:
    return REPORTS / f"{a['date']}-{a['activity_id']}.md"


def pending(days: int = 7) -> list[dict]:
    since = date.today() - timedelta(days=days)
    return [{"id": a["activity_id"], "date": a["date"], "sport": a["sport"], "name": a["name"], "minutes": round(a["minutes"]),
             "report": str(report_path(a).relative_to(ROOT))}
            for a in sources.acts() if a["start"].date() >= since and a["minutes"] >= 10 and not report_path(a).exists()]


def _zone_minutes(points: list, floors: list, field: int) -> list:
    out = [0.0] * len(floors)
    for p, q in zip(points, points[1:]):
        v, dt = p[field], q[0] - p[0]
        if v is None or dt <= 0 or dt > 1:
            continue
        z = max([i for i, f in enumerate(floors) if v >= f], default=0)
        out[z] += dt
    return [round(x, 1) for x in out]


def _halves(points: list) -> dict | None:
    """First vs second half: HR, pace/power and their ratio (aerobic decoupling)."""
    pts = [p for p in points if p[1] and (p[2] or p[3])]
    if len(pts) < 20:
        return None
    skip = 10 if pts[-1][0] > 30 else pts[-1][0] * .2  # leave out the warm-up, while HR is still rising
    pts = [p for p in pts if p[0] >= skip]
    mid = len(pts) // 2
    def stats(seg):
        hr = statistics.mean(p[1] for p in seg)
        sp = statistics.mean(p[2] for p in seg if p[2]) if any(p[2] for p in seg) else None
        pw = statistics.mean(p[3] for p in seg if p[3]) if any(p[3] for p in seg) else None
        return {"hr": round(hr, 1), "pace_min_km": round(1000 / sp / 60, 2) if sp else None, "power": round(pw) if pw else None,
                "_ratio": (sp or pw or 0) / hr}
    a, b = stats(pts[:mid]), stats(pts[mid:])
    drift = round((a["_ratio"] - b["_ratio"]) / a["_ratio"] * 100, 1) if a["_ratio"] else None
    for x in (a, b):
        x.pop("_ratio")
    return {"first_half": a, "second_half": b, "decoupling_pct": drift}


def _comparables(a: dict, n: int = 8) -> list[dict]:
    """Earlier sessions to compare with: same library workout, or same sport at similar duration and effort."""
    wid = workouts.workout_for(a)
    cands = [x for x in sources.acts() if x["start"] < a["start"] and x["sport"] == a["sport"]]
    if wid:
        same = [x for x in cands if workouts.workout_for(x) == wid]
    else:
        same = [x for x in cands if abs(x["minutes"] - a["minutes"]) <= max(15, a["minutes"] * .35)]
    out = []
    for x in same[-n:]:
        s = workouts.act_summary(x)
        speed = x["km"] * 1000 / (x["minutes"] * 60) if x["minutes"] else 0
        out.append({k: s[k] for k in ("date", "name", "minutes", "km", "avg_hr", "pace", "power", "load", "rpe")}
                   | {"m_per_beat": round(speed * 60 / s["avg_hr"], 3) if s["avg_hr"] and speed else None})
    return out


def context(aid: str) -> dict:
    a = next((x for x in sources.acts() if x["activity_id"] == aid), None)
    if not a:
        sys.exit(f"activity {aid} not found")
    det = activity.activity(aid)
    s = det["summary"]
    day = a["start"].date()
    pts = det["points"]
    zones, pz = det.get("zones"), det.get("power_zones")
    hr_zone_min = _zone_minutes(pts, zones["floors"], 1) if zones and any(p[1] for p in pts) else None
    power_zone_min = _zone_minutes(pts, pz["floors"], 3) if pz and any(p[3] for p in pts) else None
    speed = a["km"] * 1000 / (a["minutes"] * 60) if a["minutes"] else 0
    ws = store.monday(day)
    wk = week.week(ws)
    nxt = [workouts.planned_from_event(e) for e in sources.calendar(day + timedelta(days=1), day + timedelta(days=7), ("WORKOUT",))
           if not e.get("paired_activity_id")]
    notes = [{"date": e["start_date_local"][:10], "name": e["name"]} for e in sources.calendar(day - timedelta(days=35), day, ("NOTE",))]
    return {
        "report_path": str(report_path(a).relative_to(ROOT)),
        "workout": {k: s[k] for k in ("id", "date", "start", "name", "sport", "minutes", "km", "avg_hr", "max_hr", "pace",
                                       "power", "load", "rpe", "feel", "te", "notes", "compliance", "decoupling")}
                   | {"np": a.get("np"), "ftp": a.get("ftp"), "m_per_beat": round(speed * 60 / s["avg_hr"], 3) if s["avg_hr"] and speed else None},
        "planned": det.get("planned") and {k: det["planned"][k] for k in ("name", "description", "minutes", "load")},
        "zones_used": zones and {"source": zones["source"], "lthr": zones["lthr"], "floors": zones["floors"], "names": zones["names"]},
        "hr_zone_minutes_current_zones": hr_zone_min,
        "hr_zone_minutes_intervals_icu": [round(z, 1) for z in a["zones"]],
        "power_zones": pz and {"ftp": pz["ftp"], "floors": pz["floors"], "names": pz["names"]},
        "power_zone_minutes": power_zone_min,
        "sections": det.get("sections") or [],  # intervals.icu's split: WORK/RECOVERY with avg power/HR; last20_* on long work blocks
        "parts": det.get("parts") or [],  # the plan's parts from 1-s streams: avg/NP power, HR, cadence, EF, decoupling, per-rep values
        "reps": det["reps"],
        "halves": _halves(pts),
        "earlier_comparable": _comparables(a),
        "readiness_that_day": body.readiness(day),
        "fuel": _fuel(a["activity_id"]),  # quick fuel check (before/during/after) vs target, if filled in
        "load_context": (body.load_series(day, 1) or [{}])[-1],
        "week": {"focus": wk["focus"], "totals": wk["totals"], "intensity_last7": wk["intensity"], "rules": wk["rules"]},
        "next_planned": [{k: p[k] for k in ("date", "name", "sport", "minutes", "load", "description")} for p in nxt[:5]],
        "calendar_notes_last_5_weeks": notes,
        "read_also": ["coach/principles.md", "coach/rules.yaml"] + (["coach/principles.local.md"] if (ROOT / "coach" / "principles.local.md").exists() else []),
    }


def _fuel(aid: str) -> dict | None:
    from app.backend import nutrition
    try:
        f = nutrition.fuel_check(aid)
    except Exception:
        return None
    return {"target": f["target"], "log": f["log"], "verdict": f["verdict"]}


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--pending"
    if arg == "--pending":
        print(json.dumps(pending(), indent=1, ensure_ascii=False))
    else:
        aid = sources.acts()[-1]["activity_id"] if arg == "latest" else arg
        print(json.dumps(context(aid), indent=1, ensure_ascii=False, default=str))

