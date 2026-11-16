"""Single workouts: the workout list, the detail page (samples, sections, reps) and the library page."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import date, timedelta

from .store import DETAILS
from .sources import acts, analyses, events, library, power_zones_for, zones_for
from .parts import parts as plan_parts
from .workouts import act_summary, parse_steps, planned_from_event, workout_for

# sync clients in the project root (store puts it on sys.path)
from garmin.client import api_get
import intervals_sync


def activity_list(limit: int = 60, sport: str | None = None) -> list[dict]:
    rows = [a for a in acts() if not sport or a["sport"] == sport]
    return [act_summary(a) for a in reversed(rows[-limit:])]


def _details(aid: str) -> dict | None:
    DETAILS.mkdir(exist_ok=True)
    f = DETAILS / f"{aid}.json"
    if f.exists():
        return json.loads(f.read_text())
    try:
        d = api_get(f"/activity-service/activity/{aid}/details")
    except Exception:
        return None
    f.write_text(json.dumps(d))
    return d


def prefetch_details(days: int = 45, limit: int = 40) -> int:
    """Fetch and cache second-by-second data for recent activities, so opening them is instant."""
    since = date.today() - timedelta(days=days)
    todo = [a["activity_id"] for a in acts() if a["start"].date() >= since and a["activity_id"].isdigit()
            and not (DETAILS / f"{a['activity_id']}.json").exists()][-limit:]
    for aid in todo:
        _details(aid)
    return len(todo)


def activity(aid: str) -> dict:
    a = next((x for x in acts() if x["activity_id"] == aid), None)
    if not a:
        return {}
    s = act_summary(a)
    d = _details(aid) or {}
    pts, poly, reps = [], [], []
    if d.get("metricDescriptors"):
        idx = {m["key"]: m["metricsIndex"] for m in d["metricDescriptors"]}
        g = lambda m, k: m[idx[k]] if k in idx else None
        for r in d.get("activityDetailMetrics", []):
            m = r["metrics"]
            if g(m, "sumDuration") is None:
                continue
            pts.append([round(g(m, "sumDuration") / 60, 2), g(m, "directHeartRate"), g(m, "directSpeed"),
                        g(m, "directPower"), g(m, "sumDistance")])
        poly = [[p["lat"], p["lon"]] for p in (d.get("geoPolylineDTO") or {}).get("polyline", [])[::3] if p.get("lat")]
        reps = _detect_reps(pts) if a["sport"] == "run" else []
    wid = s["workout"]
    earlier = [act_summary(x) for x in acts() if wid and workout_for(x) == wid and x["start"] < a["start"]][-4:]
    zones = zones_for(a["sport"])
    sections = []
    if a.get("icu_id"):
        try:
            sections = intervals_sync.activity_sections(a["icu_id"])
        except Exception:  # offline or not analysed yet: the page works without sections
            sections = []
    ev = next((e for e in events() if a.get("paired_event_id") and str(e["id"]) == str(a["paired_event_id"])), None)
    # sections only mean something for structured sessions: a planned workout with several steps, or a library
    # interval session. On an easy run intervals.icu's auto-detected "efforts" are noise.
    lib_w = library().get(workout_for(a) or "", {})
    structured = (ev and len(parse_steps(ev.get("description"))) >= 2) or any(k == "hard" for _, k in lib_w.get("steps", []))
    if len(sections) <= 1 or not structured:
        sections = []
    planned = planned_from_event(ev) if ev else None
    by_part = []
    if ev and a.get("icu_id"):
        try:  # the plan's parts (warm-up, drills, main set) with power, HR, cadence and EF each
            by_part = plan_parts(a["icu_id"], ev.get("description"), a["sport"])
        except Exception:
            by_part = []
    power_zones = power_zones_for(a["sport"], a.get("ftp") if a["sport"] == "ride" else None)
    if power_zones:
        power_zones["np"] = a.get("np")
    return {"summary": s, "points": pts, "polyline": poly, "reps": reps, "earlier": list(reversed(earlier)), "planned": planned,
            "zones": zones, "power_zones": power_zones, "analysis": analyses().get(aid), "sections": sections, "parts": by_part,
            "repeat_number": len(earlier) + 1 if wid else None, "workout": library().get(wid) if wid else None}


def _detect_reps(pts: list) -> list[dict]:
    sp = [p[2] or 0 for p in pts]
    sm = [sum(sp[max(0, i - 1):i + 2]) / len(sp[max(0, i - 1):i + 2]) for i in range(len(sp))]
    moving = sorted(v for v in sm if v > 1)
    if not moving:
        return []
    thr = statistics.median(moving) * 1.07
    segs, cur = [], None
    for i, v in enumerate(sm):
        if v > thr and cur is None:
            cur = i
        elif v <= thr and cur is not None:
            if pts[i][0] - pts[cur][0] >= 2:
                segs.append((cur, i))
            cur = None
    out = []
    for a, b in segs:
        hs = [p[1] for p in pts[a:b] if p[1]]
        ss = [p[2] for p in pts[a:b] if p[2]]
        dist = ((pts[b][4] or 0) - (pts[a][4] or 0)) / 1000
        avg = sum(ss) / len(ss)
        if avg < statistics.median(moving) * 1.12:
            continue
        out.append({"from": pts[a][0], "to": pts[b][0], "km": round(dist, 2), "pace": round(1000 / avg / 60, 3),
                    "avg_hr": round(sum(hs) / len(hs)) if hs else None, "max_hr": max(hs) if hs else None})
    return out


def library_page() -> list[dict]:
    counts = defaultdict(list)
    for a in acts():
        w = workout_for(a)
        if w:
            counts[w].append(a["date"])
    return [w | {"count": len(counts[w["id"]]), "last": max(counts[w["id"]], default=None)} for w in library().values()]
