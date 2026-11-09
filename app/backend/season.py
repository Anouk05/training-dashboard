"""Seasons: the current season from the intervals.icu calendar, and past seasons with their results."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .store import cached, clean_name, fmt_hms, ICU_LOAD_FROM, ICU_SPORT, monday, num, PLANS, read_yaml
from .sources import acts, calendar, duplicate_stats, ev_date, events, icu_wellness, RACE_CATS
from .body import load_series
from .workouts import planned_from_event


def _season_file() -> dict | None:
    files = sorted(PLANS.glob("season-*.yaml"))
    return cached(files[-1], read_yaml) if files else None


def season() -> dict:
    """Current season from the intervals.icu calendar: the latest season start, the races after it,
    planned workouts per week, and weekly notes as phase labels."""
    t = date.today()
    starts = [e for e in events() if e["category"] == "SEASON_START" and ev_date(e) <= t]
    if not starts:
        return {}
    st = max(starts, key=ev_date)
    start = monday(ev_date(st))
    races = sorted((e for e in events() if e["category"] in RACE_CATS and ev_date(e) >= start), key=ev_date)
    end = ev_date(races[-1]) + timedelta(days=7) if races else start + timedelta(weeks=52)
    workouts = calendar(start, end, ("WORKOUT",))
    week_notes = {monday(ev_date(e)): e["name"] for e in calendar(start, end, ("NOTE",)) if e.get("for_week")}

    weeks, ws = [], start
    while ws <= end:
        we = ws + timedelta(days=6)
        pl = [planned_from_event(e) for e in workouts if ws <= ev_date(e) <= we]
        split = [sum(p["zones"][0] + p["zones"][1] for p in pl) / 60, sum(p["zones"][2] for p in pl) / 60, sum(p["zones"][3] for p in pl) / 60]
        w = {"start": ws.isoformat(), "phase": re.sub(r"\s*-\s*week \d+$", "", week_notes.get(ws, ""), flags=re.I),
             "note": week_notes.get(ws, ""), "hours": round(sum(split), 2), "split": [round(x, 2) for x in split],
             "load": sum(p["load"] for p in pl), "sessions": len(pl)}
        if ws <= t:
            wa = [a for a in acts() if ws <= a["start"].date() <= we]
            w["done_hours"] = round(sum(a["minutes"] for a in wa) / 60, 1)
            w["done_load"] = round(sum(a["load"] for a in wa))
        weeks.append(w)
        ws += timedelta(weeks=1)

    # phases = runs of consecutive weeks with the same weekly-note label
    phases = []
    for i, w in enumerate(weeks):
        if w["phase"] and phases and phases[-1]["name"] == w["phase"] and phases[-1]["index"] + phases[-1]["weeks"] == i:
            phases[-1]["weeks"] += 1
        elif w["phase"]:
            phases.append({"name": w["phase"], "start": w["start"], "weeks": 1, "focus": w["note"], "index": i})

    # fitness projection: intervals.icu-style 42-day weighted load, only as far as workouts are planned
    ctl = (load_series(t, 1) or [{}])[-1].get("fitness") or 0
    last_planned = max((i for i, w in enumerate(weeks) if w["sessions"]), default=-1)
    for i, w in enumerate(weeks):
        ws = date.fromisoformat(w["start"])
        if ws + timedelta(days=6) <= t:
            wl = icu_wellness().get((ws + timedelta(days=6)).isoformat())
            w["fitness"] = num(wl["ctl"]) if wl else None
        elif i <= last_planned:
            for _ in range(7):
                ctl += (w["load"] / 7 - ctl) / 42
            w["fitness"] = round(ctl, 1)
        else:
            w["fitness"] = None

    planned_weeks = [w for w in weeks if w["sessions"]]
    tot_h = sum(w["hours"] for w in planned_weeks)
    last = next((x for x in reversed(seasons()["seasons"]) if x["kind"] == "season"), None)
    return {"season": st["name"], "start": start.isoformat(), "end": end.isoformat(), "goal": st.get("description") or "",
            "phases": phases, "weeks": weeks, "block": None,
            "races": [{"date": e["start_date_local"][:10], "name": e["name"], "priority": e["category"][-1],
                       "km": round((e.get("distance") or 0) / 1000, 1) or None} for e in races],
            "planned_weeks": len(planned_weeks), "avg_hours": round(tot_h / len(planned_weeks), 1) if planned_weeks else 0,
            "intensity": [round(sum(w["split"][k] for w in planned_weeks) / tot_h, 2) if tot_h else 0 for k in range(3)],
            "last_season": last and {"label": last["label"], "avg_h": last["avg_h"]}}


def phase_at(phases, d: date) -> str | None:
    for p in phases:
        p0 = date.fromisoformat(p["start"])
        if p0 <= d < p0 + timedelta(weeks=p["weeks"]):
            return p["name"]
    return None


RESULT_RE = re.compile(r"race|regatta|beker|wedstrijd|marathon|time ?trial|timetrial|henley", re.I)


def _results(period: list[dict]) -> list[dict]:
    """Races found in activity names, plus 21 km runs and 150 km+ rides; same-name events within 3 days are grouped."""
    found = []
    for a in period:
        name = clean_name(a["name"])
        if re.search(r"prep|broken", name, re.I):  # race-pace training, not a race
            continue
        if RESULT_RE.search(a["name"] or ""):
            label = name
        elif a["sport"] == "run" and 20.9 <= a["km"] <= 21.6:
            place = re.sub(r" Running$| Hardlopen$", "", a["name"] or "")
            label = f"21.1 km run, {place}"
        elif a["sport"] == "ride" and a["km"] >= 150:
            label = f"{a['km']:.0f} km ride, {re.sub(r' (Road )?Cycling$| Fietsen$', '', a['name'] or '')}"
        else:
            continue
        timed = a["sport"] == "run" and (a["km"] >= 9.9)
        prev = found[-1] if found else None
        same = prev and (prev["label"] == label or prev["label"].lower().split()[:2] == label.lower().split()[:2])
        if same and (a["start"].date() - date.fromisoformat(prev["end"])).days <= 3:
            prev["end"] = a["date"]
            continue
        found.append({"label": label, "date": a["date"], "end": a["date"],
                      "time": fmt_hms(a["minutes"]) if timed else None})
    if period:
        by_icu = {a.get("icu_id"): a for a in period if a.get("icu_id")}
        for e in calendar(period[0]["start"].date(), period[-1]["start"].date(), RACE_CATS):
            a = by_icu.get(e.get("paired_activity_id")) or next((x for x in period if x["date"] == e["start_date_local"][:10]
                                                               and x["sport"] == ICU_SPORT.get(e.get("type") or "")), None)
            d = e["start_date_local"][:10]
            label = f"{e['name']} ({e['category'][-1]} race)"
            found = [f for f in found if f["date"] != d]
            prev = next((f for f in found if f["label"] == label and (date.fromisoformat(d) - date.fromisoformat(f["end"])).days <= 3), None)
            if prev:  # multi-day regatta
                prev["end"] = d
                continue
            found.append({"label": label, "date": d, "end": d, "time": fmt_hms(a["minutes"]) if a and a["sport"] == "run" else None})
        found.sort(key=lambda f: f["date"])
    return found


def _period_stats(label: str, s0: date, s1: date, kind: str, extra: dict | None = None) -> dict:
    period = [a for a in acts() if s0 <= a["start"].date() <= s1]
    weeks = ((s1 - s0).days + 1) / 7
    h = sum(a["minutes"] for a in period) / 60
    wk = defaultdict(float)
    for a in period:
        wk[monday(a["start"].date())] += a["minutes"] / 60
    mix = defaultdict(float)
    for a in period:
        mix[a["sport"]] += a["minutes"] / 60
    load_from = ICU_LOAD_FROM  # consistent (intervals.icu) training load only exists from here on
    out = {"label": label, "kind": kind, "from": s0.isoformat(), "to": s1.isoformat(), "weeks": round(weeks, 1),
           "sessions": len(period), "avg_h": round(h / weeks, 1) if weeks else 0,
           "avg_load": round(sum(a["load"] for a in period) / weeks) if weeks else 0,
           "load_complete": s0 >= load_from, "peak_h": round(max(wk.values(), default=0), 1),
           "mix": {k: round(v / h * 100) for k, v in sorted(mix.items(), key=lambda x: -x[1])} if h else {},
           "results": _results(period)}
    if extra:
        out["goals"] = extra.get("goals", [])
        out["results"] += [{"label": r, "date": None, "end": None, "time": None} for r in extra.get("results", [])]
    return out


def seasons() -> dict:
    cfg = (cached(PLANS / "seasons.yaml", read_yaml) or {}).get("seasons", [])
    out = []
    all_acts = acts()
    prev_end = all_acts[0]["start"].date() - timedelta(days=1) if all_acts else None
    starts = [e for e in events() if e["category"] == "SEASON_START" and ev_date(e) <= date.today()]
    cur_start = monday(ev_date(max(starts, key=ev_date))) if starts else None
    for s in cfg:
        s0, s1 = s["start"], s["end"]
        if prev_end and (s0 - prev_end).days > 1:
            label = "Before " + s0.strftime("%b %Y") if not out else f"Summer {s0.year}"
            out.append(_period_stats(label, prev_end + timedelta(days=1), s0 - timedelta(days=1), "off"))
        out.append(_period_stats(s["label"], s0, s1, "season", s))
        prev_end = s1
    if cur_start and prev_end:
        c0 = cur_start
        if (c0 - prev_end).days > 1:
            out.append(_period_stats(f"Summer–autumn {prev_end.year}", prev_end + timedelta(days=1), c0 - timedelta(days=1), "off"))
    hm = [{"date": a["date"], "place": clean_name(a["name"]) if " - " in (a["name"] or "") else re.sub(r" Running$| Hardlopen$", "", a["name"] or ""), "minutes": round(a["minutes"], 1),
           "time": fmt_hms(a["minutes"])} for a in all_acts if a["sport"] == "run" and 20.9 <= a["km"] <= 21.6]
    return {"seasons": out, "half_marathons": hm, "duplicates": duplicate_stats()}
