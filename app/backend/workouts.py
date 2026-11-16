"""Planned workouts: intervals.icu workout text, abilities per workout, calendar edits (move, edit, add,
delete), and the summary of a completed activity."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from .store import as_date, cached, clean_name, fmt_dur, ICU_SPORT, iso_week, LOAD_PER_HOUR, num, PLANS, read_yaml
from .sources import acts, analyses, ev_date, events, ftp_for, library

# sync clients in sync/ (store puts the project root on sys.path)
from sync import intervals as intervals_sync


def week_plan(week_start: date) -> dict:
    p = PLANS / "weeks" / f"{iso_week(week_start)}.yaml"
    return cached(p, read_yaml) or {}


def planned_session(s: dict) -> dict:
    """Expand a planned session with library info, minutes, intensity split and estimated load."""
    w = library().get(s.get("workout"), {})
    steps = w.get("steps", [])
    minutes = s.get("minutes")
    if not minutes and s.get("distance_km"):
        minutes = s["distance_km"] * 6  # ~6:00/km for easy long runs
    total = sum(m for m, _ in steps) or 1
    scale = (minutes / total) if minutes else 1
    split = defaultdict(float)
    for m, kind in steps:
        split[kind] += m * scale
    minutes = sum(split.values())
    load = sum(m / 60 * LOAD_PER_HOUR[k] for k, m in split.items())
    zones = [split["rest"], split["easy"], split["moderate"], split["hard"], 0]
    sub = []
    if s.get("distance_km"):
        sub.append(f"{s['distance_km']} km")
    sub.append(fmt_dur(minutes))
    if w.get("targets", {}).get("pace"):
        sub.append(w["targets"]["pace"])
    if s.get("note"):
        sub.append(s["note"])
    return {"date": str(s["date"]), "workout": s.get("workout"), "name": w.get("name", s.get("workout")),
            "sport": w.get("sport", "other"), "summary": w.get("summary", ""), "targets": w.get("targets", {}),
            "minutes": round(minutes), "load": round(load), "zones": [round(z) for z in zones],
            "hard_min": round(split["hard"]), "sub": " · ".join(sub),
            "steps": [[m * scale, k] for m, k in steps]}


_DUR = re.compile(r"(?:(\d+(?:\.\d+)?)h)?\s*(?:(\d+(?:\.\d+)?)m(?!tr|i))?\s*(?:(\d+)s)?", re.I)


_DIST = re.compile(r"(\d+(?:\.\d+)?)\s*(km|mtr)\b", re.I)


def _step_kind(t: str) -> str:
    """Rough intensity of one workout line in intervals.icu syntax (zone, pace, watts or %)."""
    t = t.lower()
    z = [int(x) for x in re.findall(r"z(\d)", t)]
    if z:
        top = max(z)
        return "hard" if top >= 4 else "moderate" if top == 3 else "easy"
    paces = [int(m) + int(s) / 60 for m, s in re.findall(r"(\d):(\d\d)", t)]
    if paces:
        p = min(paces)
        return "hard" if p < 5.17 else "moderate" if p < 5.67 else "easy"
    watts = [int(w) for w in re.findall(r"(\d{2,3})\s*w\b", t)]
    if watts:
        w = max(watts)
        return "hard" if w >= 180 else "moderate" if w >= 140 else "easy"
    pct = [int(x) for x in re.findall(r"(\d{2,3})\s*%", t)]
    if pct:
        return "hard" if max(pct) >= 95 else "moderate" if max(pct) >= 85 else "easy"
    return "easy"


def _step_minutes(t: str, kind: str) -> float:
    d = _DIST.search(t)
    if d:
        km = float(d[1]) / (1000 if d[2].lower() == "mtr" else 1)
        return km * (4.6 if kind == "hard" else 5.5 if kind == "moderate" else 6.2)
    m = _DUR.match(t.strip())
    if m and any(m.groups()):
        h, mi, se = (float(x) if x else 0 for x in m.groups())
        return h * 60 + mi + se / 60
    return 0


def parse_steps(desc: str | None) -> list[list]:
    """intervals.icu workout text -> [[minutes, intensity], …], expanding 'Nx' repeat blocks."""
    steps, block, mult = [], [], 1
    for line in (desc or "").splitlines() + [""]:
        s = line.strip()
        rep_ = re.match(r"^(\d+)\s*x\b", s, re.I)
        if rep_ or not s:
            steps += block * mult
            block, mult = [], int(rep_[1]) if rep_ else 1
            continue
        if s.startswith("-"):
            body = s[1:].strip()
            kind = _step_kind(body)
            mins = _step_minutes(body, kind)
            if mins:
                block.append([mins, kind])
    return steps


ABILITY_ORDER = ("AE", "MF", "SS", "ME", "AC", "SP", "T")


def step_zones(e: dict) -> list[tuple[float, int]]:
    """(seconds, zone) per step of a planned workout's text. Power targets count by % of FTP (Z1 < 56 %, Z2 < 76 %,
    Z3 < 91 %, Z4 < 106 %, Z5 < 150 %, above that Z7), heart-rate/pace targets by their zone; steps without either are skipped."""
    ftp = ftp_for(e.get("type") or "")
    out = []
    for line in (e.get("description") or "").splitlines():
        b = line.strip()
        if not b.startswith("-"):
            continue
        dm = re.search(r"(\d+(?:\.\d+)?)\s*(h|m(?!\w)|min|s(?!\w))", b)
        secs = 0 if not dm else float(dm[1]) * {"h": 3600, "m": 60, "min": 60, "s": 1}[dm[2]]
        z = [int(x) for x in re.findall(r"z(\d)", b, re.I)]
        zone = max(z) if z else None
        w = [float(x) for r in re.findall(r"(\d+)(?:\s*-\s*(\d+))?\s*w\b", b, re.I) for x in r if x]
        rel = (sum(w) / len(w) / ftp) if (w and ftp) else None  # a range like 210-225w counts at its middle
        if rel is not None:
            zone = 1 if rel < .56 else 2 if rel < .76 else 3 if rel < .91 else 4 if rel < 1.06 else 5 if rel < 1.5 else 7
        if zone is not None:
            out.append((secs, zone))
    return out


def abilities_for(e: dict) -> list[str]:
    """Friel abilities a planned workout trains. An "Abilities: AE, SS" line in the description wins; otherwise
    they're read from the steps: easy time = aerobic endurance, drills/strides/cadence = speed skills,
    hills/big gear = muscular force, sustained Z3–Z4 (≥ 3′) = muscular endurance, Z5 (≥ 2′) = aerobic capacity,
    all-out sprints (< 30″) = sprint power, and "test" in the name = testing. Strength shows the weights phase."""
    desc, name = e.get("description") or "", (e.get("name") or "")
    m = re.search(r"^\s*abilit(?:y|ies)\s*:\s*(.+)$", desc, re.I | re.M)
    if m:
        got = {x.strip().upper() for x in re.split(r"[,\s]+", m[1]) if x.strip()}
        return [a for a in ABILITY_ORDER if a in got]
    if ICU_SPORT.get(e.get("type") or "") == "str":
        files, day = sorted(PLANS.glob("atp-*.yaml")), ev_date(e)
        weeks = (cached(files[-1], read_yaml) or {}).get("weeks", []) if files else []
        w = next((w for w in weeks if as_date(w["start"]) <= day < as_date(w["start"]) + timedelta(days=7)), None)
        return [w["weights"]] if w and w.get("weights") else ["Weights"]
    text, out = (name + "\n" + desc).lower(), set()
    if "test" in name.lower():
        out.add("T")
    if re.search(r"drill|stride|cadence|rpm|single.?leg|technique|spin.?up|form", text):
        out.add("SS")
    if re.search(r"hill|big gear|low cadence|force|paddle|torque|strength endurance", text):
        out.add("MF")
    easy_min = 0.0
    for secs, zone in step_zones(e):
        if zone <= 2:
            easy_min += secs / 60
        elif zone <= 4 and secs >= 180:
            out.add("ME")
        elif zone in (5, 6) and secs >= 120:  # shorter Z5 bits are openers, not VO2 work
            out.add("AC")
        elif zone >= 5 and secs < 30 and "SS" not in out:
            out.add("SP")
    if easy_min >= 20 or (not out and re.search(r"easy|endurance|long|aerobic|z2", text)):
        out.add("AE")
    return [a for a in ABILITY_ORDER if a in out]


def event_time(e: dict) -> str | None:
    """Time of day of a planned workout ("07:30"), or None when it's only planned for the day (00:00 in intervals.icu)."""
    t = (e.get("start_date_local") or "")[11:16]
    return t if t and t != "00:00" else None


def planned_from_event(e: dict) -> dict:
    total = (e.get("moving_time") or 0) / 60
    steps = parse_steps(e.get("description"))
    if total and steps:
        k = total / (sum(m for m, _ in steps) or 1)
        steps = [[m * k, kind] for m, kind in steps]
    elif total:
        steps = [[total, "easy"]]
    split = defaultdict(float)
    for m, kind in steps:
        split[kind] += m
    minutes = sum(split.values())
    load = e.get("icu_training_load") or round(sum(m / 60 * LOAD_PER_HOUR[k] for k, m in split.items()))
    lines = [l.strip(" -") for l in (e.get("description") or "").splitlines() if l.strip()]
    km = (e.get("distance") or 0) / 1000
    return {"date": e["start_date_local"][:10], "time": event_time(e), "event_id": e["id"], "workout": None, "name": e["name"], "type": e.get("type"),
            "sport": ICU_SPORT.get(e.get("type") or "", "other"), "summary": " · ".join(lines[:4]),
            "description": e.get("description") or "", "targets": {}, "minutes": round(minutes), "load": round(load),
            "zones": [round(split["rest"]), round(split["easy"]), round(split["moderate"]), round(split["hard"]), 0],
            "hard_min": round(split["hard"]), "sub": " · ".join(x for x in [f"{km:.1f} km" if km else "", fmt_dur(minutes) if minutes else ""] if x),
            "steps": steps, "done_id": e.get("paired_activity_id"), "abilities": (ab := abilities_for(e)),
            "intensity": intensity_of(ab, sum(t for t, z in step_zones(e) if z == 3) / 60)}


def _time_of(event_id: int) -> str:
    e = next((x for x in events() if x["id"] == event_id), None)
    return (e or {}).get("start_date_local", "")[11:19] or "00:00:00"


def move_event(event_id: int, to: date) -> None:
    """Move a planned workout in intervals.icu (it follows to the watch), keeping its time of day, then refresh the
    local calendar copy."""
    intervals_sync.move_event(event_id, to, _time_of(event_id))
    intervals_sync.sync_events()


def set_time(event_id: int, time: str | None) -> None:
    """Set the time of day of a planned workout ("07:30"), or clear it (None: just planned for the day)."""
    e = next((x for x in events() if x["id"] == event_id), None)
    if not e:
        raise ValueError("planned workout not found; sync first")
    if time and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("time must be HH:MM")
    intervals_sync.move_event(event_id, date.fromisoformat(e["start_date_local"][:10]), f"{time}:00" if time else "00:00:00")
    intervals_sync.sync_events()


def update_event(event_id: int, changes: dict) -> None:
    """Edit a planned workout in intervals.icu, then refresh the local calendar copy."""
    if changes.get("date"):
        changes["start_date_local"] = f"{changes.pop('date')}T{_time_of(event_id)}"
    intervals_sync.update_event(event_id, changes)
    intervals_sync.sync_events()


def create_event(day: date, name: str, sport_type: str, description: str) -> None:
    intervals_sync.create_event(day, name, sport_type, description)
    intervals_sync.sync_events()


def delete_event(event_id: int) -> None:
    intervals_sync.delete_event(event_id)
    intervals_sync.sync_events()


def set_notes(aid: str, notes: str) -> None:
    """Notes on a completed workout live in intervals.icu (activity description)."""
    a = next((x for x in acts() if x["activity_id"] == aid), None)
    if not a or not a.get("icu_id"):
        raise ValueError("this workout isn't in intervals.icu yet; sync first")
    intervals_sync.set_activity_notes(a["icu_id"], notes)


def preview_workout(description: str, sport: str = "other") -> dict:
    """Live preview for the editor: parsed steps, duration and a rough load estimate."""
    steps = parse_steps(description)
    minutes = sum(m for m, _ in steps)
    split = defaultdict(float)
    for m, kind in steps:
        split[kind] += m
    load = round(sum(m / 60 * LOAD_PER_HOUR[k] for k, m in split.items()))
    return {"steps": steps, "minutes": round(minutes), "load": load,
            "zones": [round(split["rest"]), round(split["easy"]), round(split["moderate"]), round(split["hard"]), 0]}


def move_session(week_start: date, index: int, to: date) -> None:
    """Change the date of the index-th session, editing the YAML line in place so comments survive."""
    p = PLANS / "weeks" / f"{iso_week(week_start)}.yaml"
    lines = p.read_text().splitlines(keepends=True)
    seen = -1
    for i, line in enumerate(lines):
        if re.match(r"\s*- \{.*date:", line):
            seen += 1
            if seen == index:
                lines[i] = re.sub(r"date: \d{4}-\d{2}-\d{2}", f"date: {to.isoformat()}", line)
                p.write_text("".join(lines))
                return
    raise IndexError(index)


def act_summary(a: dict) -> dict:
    return {
        "id": a["activity_id"], "date": a["date"], "start": a["start_local"], "name": clean_name(a["name"]),
        "sport": a["sport"], "minutes": round(a["minutes"], 1), "km": round(a["km"], 2),
        "avg_hr": num(a["avg_hr"]), "max_hr": num(a["max_hr"]), "load": round(a["load"]),
        "pace": num(a["pace_min_per_km"]) if a["sport"] == "run" else None, "power": num(a["avg_power"]),
        "rpe": num(a["rpe"]), "feel": a.get("feel_label"), "te": a["te_label"], "zones": [round(z, 1) for z in a["zones"]],
        "zone_source": a.get("zone_source") or ("hr" if any(a["zones"]) else None),
        "workout": workout_for(a), "notes": a.get("notes") or "", "compliance": a.get("compliance"),
        "decoupling": a.get("decoupling"), "icu_id": a.get("icu_id"),
        "analysis": (lambda x: x and {k: x[k] for k in ("title", "rating", "flags")})(analyses().get(a["activity_id"])),
    }


def workout_for(a: dict) -> str | None:
    """Match an activity to a library workout (stable id) so repeats can be compared."""
    lib = library().values()
    for w in lib:
        if w.get("match") and w.get("sport") == a["sport"] and re.search(w["match"], a["name"] or "", re.I):
            return w["id"]
    for w in lib:
        if w.get("match_long_run_km") and a["sport"] == "run" and a["km"] >= w["match_long_run_km"]:
            return w["id"]
        if w.get("match_long_ride_min") and a["sport"] == "ride" and a["minutes"] >= w["match_long_ride_min"]:
            return w["id"]
    for w in lib:
        if w.get("match_sport") == a["sport"]:
            return w["id"]
    return None


def intensity_of(abilities: list[str], moderate_min: float = 0, hard_min: float = 0) -> str:
    """Easy, moderate or hard (Friel's 5-2 pattern): advanced abilities, tests and the gym in AA/MT/MS (breakthrough
    sessions in prep and early base) are hard; strength maintenance and tempo blocks are moderate; the rest is easy."""
    if set(abilities) & {"ME", "AC", "SP", "T"} or set(abilities) & {"AA", "MT", "MS"} or hard_min >= 10:
        return "hard"
    if "SM" in abilities or moderate_min >= 20:
        return "moderate"
    return "easy"


def is_hard(zones: list[float]) -> bool:
    return sum(zones[3:]) >= 10  # 10+ minutes at Z4 or above
