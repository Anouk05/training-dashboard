"""The Week and Today pages: week overview, coach rules, today's summary and the daily coach note."""

from __future__ import annotations

from datetime import date, timedelta

from .store import athlete_name, fmt_dur, fmt_pace, iso_week, monday, ROOT, SPORT_NAMES
from .sources import acts, calendar, ev_date, events, has_calendar, RACE_CATS, rules, zones_for
from .body import load_series, readiness
from .workouts import act_summary, is_hard, planned_from_event, planned_session, week_plan, workout_for
from .atp import sport_split_target


def week(week_start: date | None = None) -> dict:
    ws = monday(week_start or date.today())
    days = [ws + timedelta(days=i) for i in range(7)]
    today = date.today()
    done = [act_summary(a) for a in acts() if ws <= a["start"].date() <= days[-1]]
    done_icu = {a["icu_id"] for a in done if a["icu_id"]}
    if has_calendar():
        source, plan = "intervals", {}
        planned = [planned_from_event(e) for e in calendar(ws, days[-1], ("WORKOUT",))]
        # a planned workout that's been done is shown as the activity instead
        planned = [p for p in planned if not (p["done_id"] and p["done_id"] in done_icu)]
        notes = calendar(ws, days[-1], ("NOTE",) + RACE_CATS)
    else:
        source, plan = "yaml", week_plan(ws)
        planned = [planned_session(s) | {"index": i} for i, s in enumerate(plan.get("sessions", []))]
        notes = []
    week_notes = [e["name"] for e in notes if e["category"] == "NOTE" and e.get("for_week")]

    out_days = []
    for d in days:
        ds = d.isoformat()
        dn = [a for a in done if a["date"] == ds]
        pl = [p for p in planned if p["date"] == ds]
        if source == "yaml" and dn and d <= today:
            pl = []
        day_notes = [{"name": e["name"], "race": e["category"] if e["category"] in RACE_CATS else None}
                     for e in notes if ev_date(e) == d and not e.get("for_week")]
        out_days.append({"date": ds, "done": dn, "planned": pl, "notes": day_notes, "is_today": d == today})

    by_sport = {}
    for s in ("run", "ride", "swim", "str", "row"):
        dh = sum(a["minutes"] for a in done if a["sport"] == s) / 60
        dl = sum(a["load"] for a in done if a["sport"] == s)
        # planned total = what's done on past days + what's still planned on remaining days
        rem = [p for d in out_days for p in d["planned"] if p["sport"] == s]
        ph = dh + sum(p["minutes"] for p in rem) / 60
        plo = dl + sum(p["load"] for p in rem)
        by_sport[s] = {"hours": round(dh, 1), "load": round(dl), "plan_hours": round(ph, 1), "plan_load": round(plo)}
    totals = {"hours": round(sum(v["hours"] for v in by_sport.values()), 1), "load": sum(v["load"] for v in by_sport.values()),
              "plan_hours": round(sum(v["plan_hours"] for v in by_sport.values()), 1),
              "plan_load": sum(v["plan_load"] for v in by_sport.values())}

    # sport split: share of swim + bike + run time (weights left out), planned and done, against the plan's target
    tri = {"swim": "swim", "bike": "ride", "run": "run"}
    ph = {k: by_sport[s]["plan_hours"] for k, s in tri.items()}
    dh = {k: by_sport[s]["hours"] for k, s in tri.items()}
    pct = lambda h: {k: round(v / sum(h.values()) * 100) if sum(h.values()) else 0 for k, v in h.items()}
    target = sport_split_target(ws)
    split = {"planned": pct(ph), "done": pct(dh), "target": target and {k: target[k] for k in tri},
             "why": target and target.get("why"), "weights_hours": by_sport["str"]["plan_hours"]}

    # intensity: HR zone minutes over the 7 days up to today (or week end)
    end = min(today, days[-1])
    last7 = [a for a in acts() if end - timedelta(days=6) <= a["start"].date() <= end]
    zt = [sum(a["zones"][i] for a in last7 if i < len(a["zones"])) for i in range(7)]
    tz = sum(zt) or 1
    intensity = {"easy": round((zt[0] + zt[1]) / tz, 3), "moderate": round(zt[2] / tz, 3), "hard": round(sum(zt[3:]) / tz, 3),
                 "from_power": sum(1 for a in last7 if a.get("zone_source") == "power"),
                 "unmeasured": sum(1 for a in last7 if not any(a["zones"]))}

    return {"start": ws.isoformat(), "iso": iso_week(ws), "source": source, "status": plan.get("status"),
            "focus": " · ".join(week_notes) or plan.get("focus"), "days": out_days, "by_sport": by_sport, "totals": totals, "intensity": intensity, "split": split,
            "rules": check_rules(ws, out_days, totals, intensity)}


def check_rules(ws: date, out_days: list, totals: dict, intensity: dict) -> list[dict]:
    r = rules()
    res = []
    easy_min = r.get("easy_share_min", .8)
    res.append({"ok": intensity["easy"] >= easy_min,
                "text": f"At least {easy_min:.0%} easy: **{intensity['easy']:.0%}** over the last 7 days."})
    if r.get("no_back_to_back_hard"):
        hard_days = [d["date"] for d in out_days
                     if any(is_hard(a["zones"]) for a in d["done"]) or any(p["hard_min"] >= 10 for p in d["planned"])]
        b2b = [d for d in hard_days if (date.fromisoformat(d) + timedelta(days=1)).isoformat() in hard_days]
        res.append({"ok": not b2b, "text": "No hard days back to back." if not b2b else
                    f"Hard days back to back on {', '.join(date.fromisoformat(d).strftime('%a') for d in b2b)} and the day after."})
    last_week_load = sum(a["load"] for a in acts() if ws - timedelta(days=7) <= a["start"].date() < ws)
    acwr = (load_series(date.today(), 1) or [{}])[-1].get("acwr") or 0
    if last_week_load:
        ramp = totals["plan_load"] / last_week_load - 1
        cap = r.get("weekly_load_ramp_max", .1)
        exempt = acwr < r.get("ramp_exempt_acwr_below", .9)
        res.append({"ok": ramp <= cap or exempt, "warn": ramp > cap and exempt,
                    "text": f"Planned load is **{ramp:+.0%}** on last week. " + (
                        "Within the cap." if ramp <= cap else
                        f"The cap is +{cap:.0%}, but you're coming off light weeks (ACWR {acwr:.2f}), so this is fine once." if exempt else
                        f"The cap is +{cap:.0%}: trim a session.")})
    res.append({"ok": acwr <= r.get("acwr_max", 1.3), "text": f"Load ratio (ACWR) **{acwr:.2f}**, limit {r.get('acwr_max', 1.3)}."})
    return res


def today() -> dict:
    t = date.today()
    wk = week(t)
    session = None
    for d in wk["days"]:
        if d["date"] >= t.isoformat() and d["planned"]:
            session = d["planned"][0] | {"is_today": d["date"] == t.isoformat()}
            break
    if session is None and has_calendar():
        nxt = [planned_from_event(e) for e in calendar(t, t + timedelta(days=21), ("WORKOUT",)) if not e.get("paired_activity_id")]
        if nxt:
            session = nxt[0] | {"is_today": False}
    last_time = None
    if session and session.get("event_id"):
        prev = [e for e in events() if e["category"] == "WORKOUT" and e["name"] == session["name"]
                and e.get("paired_activity_id") and ev_date(e) < t]
        by_icu = {a.get("icu_id"): a for a in acts() if a.get("icu_id")}
        hits = [by_icu[e["paired_activity_id"]] for e in prev if e["paired_activity_id"] in by_icu]
        if hits:
            a = act_summary(hits[-1])
            last_time = {"date": a["date"], "pace": a["pace"], "avg_hr": a["avg_hr"], "power": a["power"]}
    elif session and session.get("workout"):
        reps = [a for a in acts() if workout_for(a) == session["workout"]]
        if reps:
            a = act_summary(reps[-1])
            last_time = {"date": a["date"], "pace": a["pace"], "avg_hr": a["avg_hr"], "power": a["power"]}
    ls = load_series(t, 90)
    yesterday = [act_summary(a) for a in acts() if a["start"].date() == t - timedelta(days=1)]
    today_notes = [e["name"] for e in calendar(t, t, ("NOTE",)) if not e.get("for_week")]
    recent = [act_summary(a) for a in acts() if a["start"].date() >= t - timedelta(days=2)]
    latest_analysis = next(({"id": a["id"], "date": a["date"], "sport": a["sport"], **a["analysis"]}
                            for a in reversed(recent) if a["analysis"]), None)
    return {"date": t.isoformat(), "name": athlete_name(), "readiness": readiness(t), "session": session, "last_time": last_time,
            "week": wk, "load": ls, "coach": coach_note(t, readiness(t), yesterday, today_notes),
            "latest_analysis": latest_analysis}


def coach_note(t: date, rd: dict, yesterday: list[dict], notes: list[str] | None = None) -> dict:
    """Deterministic note until Claude's daily analysis (reports/coach/<date>.md) exists."""
    f = ROOT / "reports" / "coach" / f"{t.isoformat()}.md"
    if f.exists():
        return {"source": "claude", "paragraphs": [p.strip() for p in f.read_text().split("\n\n") if p.strip()]}
    paras = []
    flagged = [r["title"].split(" ·")[0] for r in rd["reasons"] if r["status"] != "ok"]
    if rd["verdict"]:
        lead = (f"All {len(rd['reasons'])} recovery signals look good." if not flagged
                else f"Keep an eye on: {', '.join(flagged).lower()}.")
        paras.append(f"{lead} **{rd['advice']}**")
    zr = zones_for("run")
    for a in yesterday:
        if a["sport"] == "run" and a["avg_hr"] and a["pace"]:
            easy = zr and a["avg_hr"] < zr["floors"][2]  # Z1–Z2
            paras.append(f"Yesterday's {a['km']:.1f} km at {fmt_pace(a['pace'])}/km and {a['avg_hr']:.0f} bpm was "
                         + ("truly easy under your zones." if easy else "a solid aerobic effort."))
        elif a["minutes"] >= 20:
            paras.append(f"Yesterday: {SPORT_NAMES[a['sport']].lower()} {fmt_dur(a['minutes'])}"
                         + (f" at {a['power']:.0f} W" if a["power"] else "") + ".")
    for n in notes or []:
        paras.append(f"Your calendar note for today: **{n}**")
    for a in yesterday:
        if a["notes"]:
            paras.append(f"Your note on yesterday's {SPORT_NAMES[a['sport']].lower()}: “{a['notes'][:160]}{'…' if len(a['notes']) > 160 else ''}”")
            break
    return {"source": "auto", "paragraphs": paras}
