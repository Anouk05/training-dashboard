"""Strength training: the gym sessions you log in Notion (notion_data/strength.csv), the weight-lifting phase from the
annual plan, the phase guide from coach/strength.md, and a suggestion per exercise for the next session."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .store import cached, num, PLANS, read_csv, read_yaml, ROOT
from .sources import acts, calendar, icu_activities

# sync client in the project root (store puts it on sys.path)
from notion.log import ROUTINE

LOG = ROOT / "notion_data" / "strength.csv"
GUIDE = ROOT / "coach" / "strength.md"
STEP = 2.5  # kg: smallest sensible load change on most machines and bars


# --------------------------------------------------------------------------- phase guide

def _range(s: str) -> list[float]:
    """'15–20' -> [15, 20]; '60, 85' -> [60, 85]; '1' -> [1, 1]; 'indefinite' -> []."""
    v = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s or "")]
    return v if len(v) != 1 else v * 2


def phases() -> dict[str, dict]:
    """The phase table in coach/strength.md, by code (AA, MT, MS, SM)."""
    out = {}
    text = GUIDE.read_text() if GUIDE.exists() else ""
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 9 and re.fullmatch(r"[A-Z]{2}", cells[0]):
            code, name, period, total, week, load, sets, reps, rest = cells
            out[code] = {"code": code, "name": name, "period": period, "total": total, "per_week": week, "load": load,
                         "sets": sets, "reps": reps, "rest": rest, "load_pct": _range(load), "reps_rng": _range(reps),
                         "sets_rng": _range(sets), "total_rng": _range(total)}
    return out


def _atp_weeks() -> list[dict]:
    files = sorted(PLANS.glob("atp-*.yaml"))
    return (cached(files[-1], read_yaml) or {}).get("weeks", []) if files else []


def phase_on(day: date) -> str | None:
    """Weights phase (AA/MT/MS/SM) of the annual-plan week that contains this day."""
    for w in _atp_weeks():
        ws = w["start"] if isinstance(w["start"], date) else date.fromisoformat(str(w["start"]))
        if ws <= day < ws + timedelta(days=7):
            return w.get("weights") or None
    return None


# --------------------------------------------------------------------------- the log

def _reps(raw: str, sets: float | None) -> list[int]:
    """'15' (with 3 sets) -> [15, 15, 15]; '15, 15, 12' -> [15, 15, 12]; '3x15' -> [15, 15, 15]; '40s' -> [] (a hold)."""
    raw = (raw or "").lower().replace("×", "x")
    m = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", raw)
    if m:
        return [int(m[2])] * int(m[1])
    if re.search(r"\d\s*(s|sec|min)\b", raw):
        return []
    v = [int(x) for x in re.findall(r"\d+", raw)]
    if len(v) == 1 and sets and sets > 1:
        return v * int(sets)
    return v


def est_1rm(kg: float | None, reps: int) -> float | None:
    """Epley estimate; above ~12 reps it overestimates, so those sets are only a rough guide."""
    if not kg or not reps:
        return None
    return round(kg * (1 + min(reps, 20) / 30), 1)


def entries() -> list[dict]:
    out = []
    for r in cached(LOG, read_csv) or []:
        kg, sets = num(r["kg"]), num(r["sets"])
        reps = _reps(r["reps"], sets)
        out.append({"date": r["date"], "exercise": r["exercise"], "sets": int(sets) if sets else len(reps) or None,
                    "reps": reps, "reps_text": r["reps"], "kg": kg, "rpe": num(r["rpe"]), "note": r.get("note") or "",
                    "volume": round(kg * sum(reps)) if kg and reps else None,
                    "e1rm": est_1rm(kg, min(reps)) if reps else None, "phase": phase_on(date.fromisoformat(r["date"]))})
    return out


def _best_1rm(rows: list[dict], before: str | None = None) -> float | None:
    """Best estimate from the last 6 weeks, preferring sets of 12 reps or fewer (more reliable)."""
    last = rows[-1]["date"] if rows else None
    cutoff = (date.fromisoformat(last) - timedelta(days=42)).isoformat() if last else ""
    recent = [r for r in rows if r["e1rm"] and r["date"] >= cutoff]
    good = [r["e1rm"] for r in recent if r["reps"] and min(r["reps"]) <= 12]
    return max(good or [r["e1rm"] for r in recent] or [0]) or None


def _round(kg: float) -> float:
    return round(kg / STEP) * STEP


# --------------------------------------------------------------------------- suggestions

def known_maxes() -> dict[str, float]:
    """One-rep maxes you entered yourself (plans/strength.yaml), by exercise name in lower case."""
    f = PLANS / "strength.yaml"
    return {k.lower(): float(v) for k, v in ((cached(f, read_yaml) or {}).get("maxes") or {}).items() if v} if f.exists() else {}


def max_for(exercise: str, rows: list[dict]) -> tuple[float | None, str]:
    """Your own max if you gave one, otherwise the estimate from your logged sets."""
    km = known_maxes().get(exercise.lower())
    return (km, "yours") if km else (_best_1rm(rows), "estimated")


def session_rpe(day: str) -> float | None:
    """RPE you gave the gym session itself in intervals.icu (Notion lines rarely carry one)."""
    r = [num(a.get("rpe")) for a in icu_activities() if a.get("date") == day and a.get("type") == "WeightTraining"]
    return max([x for x in r if x], default=None)


def suggest(rows: list[dict], phase: dict | None, exercise: str = "") -> dict | None:
    """Next session for one exercise as concrete sets × reps @ load, from the phase guide, your max and how the last
    session went: add ~2 reps per session up to the top of the range, then add load and start again at the bottom."""
    if not phase:
        return None
    exercise = exercise or (rows[-1]["exercise"] if rows else "")
    lo, hi = [int(x) for x in (phase["reps_rng"] + [0, 0])[:2]]
    pct = phase["load_pct"]
    e1, src = max_for(exercise, rows)
    sets = int(phase["sets_rng"][0]) if phase["sets_rng"] else 3
    band = (_round(e1 * pct[0] / 100), _round(e1 * pct[-1] / 100)) if e1 and pct else None
    guide = f" · {phase['code']} guide {int(pct[0])}–{int(pct[-1])}% of {e1:g} kg ({src}) = {band[0]:g}–{band[1]:g} kg" if band else ""
    out = lambda n, r, kg, why: {"text": f"{n} × {r}" + (f" @ {kg:g} kg" if kg else ""), "sets": n, "reps": r, "kg": kg, "why": why + guide}
    if phase["code"] == "SM":
        if not e1:
            return {"text": "1 × 12 light, 1 × 6 heavy", "sets": 2, "reps": None, "kg": None, "why": ""}
        return {"text": f"1 × 12 @ {_round(e1 * .60):g} kg, 1 × 6 @ {_round(e1 * .85):g} kg", "sets": 2, "reps": None,
                "kg": _round(e1 * .85), "why": "strength maintenance" + guide}
    last = rows[-1] if rows else None
    if last and not last["reps"] and re.search(r"(\d+)\s*(s|sec)\b", last["reps_text"] or ""):  # a hold, e.g. "40s"
        secs = int(re.search(r"(\d+)\s*(s|sec)\b", last["reps_text"])[1])
        return {"text": f"{sets} × {secs + 5} s", "sets": sets, "reps": None, "kg": None, "why": "hold 5 s longer than last time"}
    if not last or not last["reps"]:
        kg = (band[0] if band else (last or {}).get("kg"))
        return out(sets, lo, kg, "start at the bottom of the range" if not last else "no reps logged last time")
    if not last["kg"]:  # bodyweight: progress reps
        return out(sets, min(hi, max(lo, min(last["reps"]) + 2)), None, "bodyweight: 2 reps more than last time")
    done = min(last["reps"])
    rpe = last["rpe"] or session_rpe(last["date"])
    cap = 6 if phase["code"] in ("AA", "MT") else 7
    if rpe and rpe > cap and phase["code"] in ("AA", "MT"):  # harder than the phase intends: repeat it, don't build
        return out(sets, done, last["kg"], f"last session felt hard (RPE {rpe:g}): repeat it until it feels easier")
    hard = (rpe or 0) >= 8
    easy = rpe is None or rpe <= cap
    kg, reps, why = last["kg"], min(hi, max(lo, done + 2)), "same load, 2 reps more"
    if done >= hi and easy:
        kg, reps, why = max(_round(last["kg"] * 1.05), last["kg"] + STEP), lo, "all sets at the top of the range: more load, back to the bottom"
    elif done < lo or hard:
        reps, why = lo, "below the range or very hard: same load, bottom of the range"
    if band and phase["code"] in ("AA", "MT"):
        if kg < band[0] - STEP:
            kg, reps, why = band[0], lo, f"lighter than the {phase['code']} range for your max: go up to its bottom"
        elif kg > band[1] + STEP:
            why = f"heavier than the {phase['code']} range ({round(kg / e1 * 100)}% of your max): keep the load, build reps"
    if phase["code"] in ("MT", "MS") and band:  # heavier phases: aim at the middle of the %-of-max range
        kg, reps, why = _round(e1 * sum(pct) / len(pct) / 100), lo, f"{int(sum(pct) / len(pct))}% of your max"
    return out(sets, reps, kg, why)


# --------------------------------------------------------------------------- pages

def overview() -> dict:
    """Progress → Strength: the phase now, sessions done in it, and per exercise its history and next target."""
    ph = phases()
    today = date.today()
    code = phase_on(today)
    rows = entries()
    by_ex = defaultdict(list)
    for r in rows:
        by_ex[r["exercise"]].append(r)
    sessions = sorted({r["date"] for r in rows}, reverse=True)
    in_phase = [d for d in sessions if phase_on(date.fromisoformat(d)) == code] if code else []
    return {"phase": ph.get(code) if code else None, "phases": list(ph.values()), "sessions_in_phase": len(in_phase),
            "sessions": [day(d, rows) for d in sessions[:8]],
            "exercises": [{"exercise": ex, "history": h[-20:], "best_1rm": max_for(ex, h)[0], "max_source": max_for(ex, h)[1],
                           "last": h[-1], "next": suggest(h, ph.get(code), ex)} for ex, h in sorted(by_ex.items(), key=lambda x: x[1][0]["date"])],
            "guide_file": "coach/strength.md", "logged": bool(rows)}


def day(d: str, rows: list[dict] | None = None) -> dict:
    """One gym session: exercises with sets, reps, load, volume and estimated max; matched to the Garmin activity."""
    rows = [r for r in (rows if rows is not None else entries()) if r["date"] == d]
    act = next((a for a in acts() if a["sport"] == "str" and a["date"] == d), None)
    return {"date": d, "phase": phase_on(date.fromisoformat(d)), "exercises": rows,
            "volume": sum(r["volume"] or 0 for r in rows), "sets": sum(r["sets"] or 0 for r in rows),
            "activity_id": act and act["activity_id"], "minutes": act and round(act["minutes"])}


def notion_plan(ahead: int = 14, back: int = 7) -> list[dict]:
    """Gym sessions to show in Notion: strength workouts planned in intervals.icu from a week ago to two weeks ahead,
    plus days you logged. Each gets the exercises of your latest session with a proposed sets × reps × load."""
    today = date.today()
    rows = entries()
    planned = {e["start_date_local"][:10] for e in calendar(today - timedelta(days=back), today + timedelta(days=ahead), ("WORKOUT",))
               if (e.get("type") or "") == "WeightTraining"}
    logged = {r["date"] for r in rows if r["date"] >= (today - timedelta(days=back)).isoformat()}
    ph = phases()
    out = []
    for d in sorted(planned | logged):
        before = [r for r in rows if r["date"] < d]
        last_day = max((r["date"] for r in before), default=None)
        # your routine (the Notion template) plus anything else you did last time
        names = list(ROUTINE) + [r["exercise"] for r in before if r["date"] == last_day or r["date"] == d]
        names = list(dict.fromkeys(n for n in names))
        code = phase_on(date.fromisoformat(d))
        p = ph.get(code) if code else None
        exercises = []
        for ex in names:
            sug = suggest([r for r in before if r["exercise"] == ex], p, ex)
            exercises.append({"exercise": ex, "planned": sug["text"] if sug else "", **({k: sug[k] for k in ("sets", "reps", "kg")} if sug else {})})
        guide = (f"{p['name']} ({code}): {p['sets']} sets of {p['reps']} reps at {p['load']}% of your max, "
                 f"{p['rest']} min rest. {p['per_week']} sessions per week, {p['total']} in total.") if p else ""
        out.append({"date": d, "name": f"Gym {code or ''} · {date.fromisoformat(d).strftime('%a %-d %b')}".replace("  ", " "),
                    "phase": code, "guide": guide, "done": d in {r["date"] for r in rows}, "exercises": exercises})
    return out
