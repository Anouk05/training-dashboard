"""The body: load model (fitness, fatigue, form), menstrual cycle phase, readiness and the Recovery page."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta

from .store import clean_name, num
from .sources import acts, calendar, cycles, daily, icu_wellness, rules


def daily_load() -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for a in acts():
        out[a["start"].date()] += a["load"]
    return out


def load_series(end: date | None = None, days: int = 120) -> list[dict]:
    """Fitness, fatigue and ACWR per day. Uses intervals.icu's CTL/ATL (42/7-day weighted) where available,
    otherwise a 28/7-day mean of daily load."""
    dl = daily_load()
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    first = start - timedelta(days=28)
    vals = [dl.get(first + timedelta(days=i), 0.0) for i in range((end - first).days + 1)]
    out = []
    for i in range(28, len(vals)):
        d = first + timedelta(days=i)
        acute = sum(vals[i - 6:i + 1]) / 7
        chronic = sum(vals[i - 27:i + 1]) / 28
        w = icu_wellness().get(d.isoformat())
        if w and num(w["ctl"]) is not None:
            chronic, acute = num(w["ctl"]), num(w["atl"])
        out.append({"date": d.isoformat(), "load": round(vals[i], 1), "fatigue": round(acute, 1),
                    "fitness": round(chronic, 1), "acwr": round(acute / chronic, 2) if chronic else None})
    return out


# Form zones as % of fitness (intervals.icu's definitions): form = fitness − fatigue
FORM_ZONES = [  # (lower bound %, upper bound %, key, label)
    (20, 999, "transition", "Transition: losing fitness"),
    (5, 20, "fresh", "Fresh: recovered, ready to race"),
    (-10, 5, "neutral", "Neutral"),
    (-30, -10, "productive", "Productive: building fitness"),
    (-999, -30, "risk", "Overtraining risk"),
]


def form_zone(pct: float | None) -> str | None:
    if pct is None:
        return None
    return next(k for lo, hi, k, _ in FORM_ZONES if lo <= pct < hi)


def fitness(days: int = 180, ahead: int = 14) -> dict:
    """Fitness, fatigue, form (absolute and % of fitness) per day, plus a projection from planned workouts."""
    t = date.today()
    series = load_series(t, days)
    by_day = defaultdict(list)
    for a in acts():
        if a["start"].date() > t - timedelta(days=days):
            by_day[a["date"]].append({"id": a["activity_id"], "name": clean_name(a["name"]), "sport": a["sport"], "load": round(a["load"])})
    out = []
    for r in series:
        form = r["fitness"] - r["fatigue"]
        pct = form / r["fitness"] * 100 if r["fitness"] else None
        out.append(r | {"form": round(form, 1), "form_pct": round(pct, 1) if pct is not None else None, "zone": form_zone(pct),
                        "activities": by_day.get(r["date"], [])})
    # projection: intervals.icu's 42/7-day weighting applied to planned (not yet done) workouts
    ctl, atl = (series[-1]["fitness"], series[-1]["fatigue"]) if series else (0, 0)
    planned = defaultdict(list)
    for e in calendar(t + timedelta(days=1), t + timedelta(days=ahead), ("WORKOUT",)):
        if not e.get("paired_activity_id"):
            planned[e["start_date_local"][:10]].append({"name": e["name"], "load": e.get("icu_training_load") or 0})
    proj = []
    for i in range(1, ahead + 1):
        d = (t + timedelta(days=i)).isoformat()
        load = sum(p["load"] for p in planned[d])
        ctl += (load - ctl) / 42
        atl += (load - atl) / 7
        form = ctl - atl
        pct = form / ctl * 100 if ctl else None
        proj.append({"date": d, "load": load, "fitness": round(ctl, 1), "fatigue": round(atl, 1), "form": round(form, 1),
                     "form_pct": round(pct, 1) if pct is not None else None, "zone": form_zone(pct), "planned": planned[d]})
    last_planned = max((i for i, p in enumerate(proj) if p["planned"]), default=-1)
    w = icu_wellness().get(t.isoformat()) or icu_wellness().get((t - timedelta(days=1)).isoformat()) or {}
    return {"series": out, "projection": proj[:last_planned + 1], "ramp_rate": num(w.get("ramp_rate")),
            "zones": [{"from": lo, "to": hi, "key": k, "label": lbl} for lo, hi, k, lbl in FORM_ZONES]}


PHASES = {"menstrual": "Menstrual", "follicular": "Follicular", "ovulation": "Ovulation", "luteal": "Luteal"}


def cycle_day(day: date) -> dict | None:
    """Cycle phase on a day, from Garmin's cycle tracking: menstrual (period), follicular, ovulation (Garmin's fertile
    window) and luteal (from the end of the fertile window to the next period)."""
    for c in reversed(cycles()):
        st = date.fromisoformat(c["start"])
        if day < st:
            continue
        end = date.fromisoformat(c["end"]) if c.get("end") else None
        if end and day > end:
            return None  # a gap between tracked cycles
        n = (day - st).days + 1
        period, fs, fl = int(num(c["period_length"]) or 5), int(num(c["fertile_start"]) or 0), int(num(c["fertile_length"]) or 0)
        phase = ("menstrual" if n <= period else "follicular" if fs and n < fs else
                 "ovulation" if fs and n < fs + fl else "luteal")
        return {"day": n, "phase": phase, "name": PHASES[phase], "cycle_start": c["start"],
                "cycle_length": int(num(c["cycle_length"]) or 0) or None, "ongoing": bool(c.get("ongoing"))}
    return None


def _phase_baseline(end: date, phase: str, field: str, days: int = 120) -> tuple[float | None, int]:
    """Median of a daily metric over earlier days in the same cycle phase (and how many days that is)."""
    d = daily()
    vals = []
    for i in range(1, days):
        k = end - timedelta(days=i)
        c = cycle_day(k)
        v = num(d.get(k.isoformat(), {}).get(field))
        if c and c["phase"] == phase and v:
            vals.append(v)
    return (statistics.median(vals) if vals else None), len(vals)


def _rhr_median(end: date) -> float | None:
    d = daily()
    vals = [num(d.get((end - timedelta(days=i)).isoformat(), {}).get("resting_hr")) for i in range(30)]
    vals = [v for v in vals if v]
    return statistics.median(vals) if vals else None


def readiness(day: date | None = None) -> dict:
    day = day or date.today()
    d = daily()
    row = d.get(day.isoformat()) or d.get((day - timedelta(days=1)).isoformat()) or {}
    hrv, lo, hi = num(row.get("hrv_last_night")), num(row.get("hrv_baseline_low")), num(row.get("hrv_baseline_high"))
    sleep, sleep_h = num(row.get("sleep_score")), num(row.get("sleep_h"))
    rhr, med = num(row.get("resting_hr")), _rhr_median(day)
    acwr = (load_series(day, 1) or [{}])[-1].get("acwr")

    # Menstrual cycle: resting HR rises and HRV drops in the second half of the cycle, so judge both against
    # earlier days in the same phase once there are enough of them (otherwise the usual 30-day / Garmin baselines).
    cyc, rhr_ref, hrv_shift = cycle_day(day), "30-day median", 0.0
    if cyc:
        prhr, n = _phase_baseline(day, cyc["phase"], "resting_hr")
        if prhr and n >= 5:
            med, rhr_ref = prhr, f"{cyc['phase']}-phase median"
        phrv, n = _phase_baseline(day, cyc["phase"], "hrv_last_night")
        allhrv = [num(daily().get((day - timedelta(days=i)).isoformat(), {}).get("hrv_last_night")) for i in range(1, 60)]
        allhrv = [v for v in allhrv if v]
        if phrv and n >= 5 and allhrv:
            hrv_shift = min(0.0, phrv - statistics.median(allhrv))  # only ever lowers the bar
    parts, reasons = [], []
    if cyc:
        expect = {"menstrual": "energy can be lower in the first days; resting HR is usually at its lowest",
                  "follicular": "usually the best phase for hard sessions and high intensity",
                  "ovulation": "resting HR starts to rise around now",
                  "luteal": "resting HR runs higher and HRV lower than usual; that alone is not fatigue"}[cyc["phase"]]
        reasons.append({"status": "ok", "title": f"Cycle day {cyc['day']} · {cyc['name'].lower()} phase",
                        "detail": expect + (" · HR and HRV judged against your earlier days in this phase" if rhr_ref != "30-day median" else "")})
    if hrv and lo and hi and hrv_shift:
        lo, hi = lo + hrv_shift, hi + hrv_shift
    if hrv and lo and hi:
        score = min(95, 65 + (hrv - lo) / (hi - lo) * 25) if hrv >= lo else max(0, 65 - (lo - hrv) * 6)
        parts.append((score, .35))
        ok = lo <= hrv <= hi or hrv > hi
        reasons.append({"status": "ok" if ok else "warn", "title": f"HRV {hrv:.0f} ms",
                        "detail": (f"inside your normal {lo:.0f}–{hi:.0f}" if lo <= hrv <= hi else
                        (f"above your normal {lo:.0f}–{hi:.0f}" if hrv > hi else f"below your normal {lo:.0f}–{hi:.0f}"))
                        + (f" for the {cyc['phase']} phase" if hrv_shift else "")})
    if sleep:
        parts.append((sleep, .25))
        reasons.append({"status": "ok" if sleep >= 70 else "warn", "title": f"Slept {sleep_h or 0:.1f} h · score {sleep:.0f}",
                        "detail": f"deep {num(row.get('deep_h')) or 0:.1f} h · REM {num(row.get('rem_h')) or 0:.1f} h"})
    if rhr and med:
        parts.append((max(0, min(100, 75 - (rhr - med) * 9)), .2))
        diff = rhr - med
        reasons.append({"status": "ok" if diff <= 1 else "warn" if diff <= 4 else "bad", "title": f"Resting HR {rhr:.0f} bpm",
                        "detail": (f"{round(diff):+d} vs" if round(diff) else "same as") + f" your {rhr_ref} ({med:.0f})" + (", not a concern" if diff <= 2 else "")})
    if acwr:
        parts.append((max(0, min(100, 100 - abs(acwr - 1) * 120)), .2))
        fresh = acwr < 0.9
        reasons.append({"status": "ok" if acwr <= rules().get("acwr_max", 1.3) else "warn",
                        "title": ("Fresh legs" if fresh else "Load in balance" if acwr <= 1.3 else "Load is high") + f" · ACWR {acwr:.2f}",
                        "detail": "recent weeks were light, room for a hard session" if fresh else
                        "steady training, recovery on track" if acwr <= 1.3 else "you've ramped up fast, keep today easy"})
    w = sum(p[1] for p in parts)
    score = round(sum(p[0] * p[1] for p in parts) / w) if w else None
    verdict = (None if score is None else "Primed" if score >= 80 else "Ready for quality" if score >= 60
               else "Easy day" if score >= 40 else "Rest")
    advice = {"Primed": "A great day for your hardest session.", "Ready for quality": "Good to go for a quality session.",
              "Easy day": "Keep it easy today; swap intensity for Z2.", "Rest": "Take a rest day or very light movement."}.get(verdict, "")
    return {"date": day.isoformat(), "score": score, "verdict": verdict, "advice": advice, "reasons": reasons, "cycle": cyc}


def recovery(days: int = 365) -> dict:
    d = daily()
    end = date.today()
    keys = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    rhr_all = [num(d[k]["resting_hr"]) for k in keys if k in d and num(d[k]["resting_hr"])]
    med = statistics.median(rhr_all) if rhr_all else 0
    rows, flags = [], []
    for k in keys:
        r = d.get(k, {})
        rhr = num(r.get("resting_hr"))
        bad = rhr and rhr >= med + 20
        if bad:
            flags.append({"date": k, "resting_hr": rhr})
        cyc = cycle_day(date.fromisoformat(k))
        rows.append({"date": k, "hrv": num(r.get("hrv_last_night")), "rhr": None if bad else rhr, "phase": cyc and cyc["phase"],
                     "sleep": num(r.get("sleep_score")), "sleep_h": num(r.get("sleep_h")), "bb": num(r.get("body_battery_max"))})
    groups = []
    for f in flags:  # group consecutive flagged days into ranges
        if groups and (date.fromisoformat(f["date"]) - date.fromisoformat(groups[-1]["to"])).days <= 3:
            groups[-1]["to"] = f["date"]
            groups[-1]["values"].append(f["resting_hr"])
        else:
            groups.append({"from": f["date"], "to": f["date"], "values": [f["resting_hr"]]})
    for g in groups:
        g0 = date.fromisoformat(g["from"])
        g["notes"] = [{"date": e["start_date_local"][:10], "name": e["name"]}
                      for e in calendar(g0 - timedelta(days=14), date.fromisoformat(g["to"]), ("NOTE",))]
    last = d.get(end.isoformat()) or d.get((end - timedelta(days=1)).isoformat()) or {}
    sleep30 = sum(1 for r in rows[-30:] if r["sleep"])
    # cycle: medians per phase over the tracked days, to show how the cycle moves resting HR, HRV and sleep
    tracked = [r for r in rows if r["phase"]]
    by_phase = []
    for ph in PHASES:
        rs = [r for r in tracked if r["phase"] == ph]
        med_of = lambda k: (round(statistics.median(v)) if (v := [r[k] for r in rs if r[k]]) else None)
        if rs:
            by_phase.append({"phase": ph, "name": PHASES[ph], "days": len(rs), "rhr": med_of("rhr"), "hrv": med_of("hrv"), "sleep": med_of("sleep")})
    cur = cycle_day(end)
    cycle = cur and {**cur, "next_period": (date.fromisoformat(cur["cycle_start"]) + timedelta(days=cur["cycle_length"] or 28)).isoformat(),
                     "cycles": len(cycles()), "since": cycles()[0]["start"], "phases": by_phase}
    return {"series": rows, "flags": groups, "median_rhr": med, "sleep_nights_30": sleep30, "cycle": cycle,
            "today": {k: num(last.get(k)) for k in ("hrv_last_night", "hrv_baseline_low", "hrv_baseline_high", "resting_hr",
                                                    "sleep_score", "sleep_h", "body_battery_max")} | {"hrv_status": last.get("hrv_status")}}
