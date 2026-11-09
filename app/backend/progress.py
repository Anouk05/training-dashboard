"""The Progress page: efficiency factor on steady sessions, and tests per sport."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from .store import cached, clean_name, num, PLANS, read_yaml, ROOT
from .sources import acts, analyses, events, library, settings_for, zones_for
from .workouts import abilities_for, act_summary, workout_for
from .season import seasons


def _with_efficiency(a: dict) -> dict:
    """Effort-normalised output: runs = metres per heartbeat, rides = watts per heartbeat
    (normalised power ÷ average HR, the "efficiency factor"; speed on a bike depends too much on wind and terrain)."""
    s = act_summary(a)
    hr = s["avg_hr"]
    if a["sport"] == "ride":
        watts = a.get("np") or num(a["avg_power"])
        eff = round(watts / hr, 2) if watts and hr else None
    else:
        speed = a["km"] * 1000 / (a["minutes"] * 60) if a["minutes"] else 0
        eff = round(speed * 60 / hr, 3) if speed and hr else None
    return s | {"eff": eff, "m_per_beat": eff if a["sport"] != "ride" else None}


TESTS_LIB = ROOT / "library" / "tests.yaml"


TESTS_LOG = PLANS / "tests.yaml"


PROGRESS_SPORTS = ("run", "ride", "swim", "strength")


EF_SKIP_NAME = re.compile(r"test|race|time ?trial|timetrial|tempo|interval|threshold|sweet ?spot|vo2|stride|fartlek|hill|"
                          r"\b\d+ ?x|x ?\d+\b|marathon|\bloop\b|(hm|10 ?k|5 ?k|race|threshold|tempo) ?pace|openers", re.I)


EF_KEEP_NAME = re.compile(r"aerobic (test|baseline)", re.I)


def _ef_check(a: dict, sport: str) -> str | None:
    """Why a session can't be used for the efficiency factor (None = it can). EF only means something on
    steady aerobic sessions: tests, races, intervals and surges raise HR and output in ways that aren't fitness."""
    zones = (zones_for(sport) or {}).get("floors") or [0, 0, 999, 999, 999, 999]
    hr, name = num(a["avg_hr"]), a["name"] or ""
    if a["sport"] != sport or not hr:
        return "no heart rate"
    if a["minutes"] < {"run": 25, "ride": 40, "swim": 20}[sport]:
        return "too short"
    if EF_SKIP_NAME.search(name) and not EF_KEEP_NAME.search(name):
        return "test, race or intervals"
    ev = next((e for e in events() if e.get("paired_activity_id") == a.get("icu_id") and e["category"] == "WORKOUT"), None) if a.get("icu_id") else None
    if ev and set(abilities_for(ev)) & {"ME", "AC", "SP", "MF", "T"}:
        return "structured workout with harder blocks"
    if hr >= zones[2]:
        return "average heart rate in Z3 or higher"
    if len(zones) > 4 and num(a["max_hr"]) and num(a["max_hr"]) >= zones[4]:
        return "contains a hard surge"
    np_, avg_p, ftp = a.get("np"), num(a["avg_power"]), num(a.get("ftp"))
    if sport == "ride":
        if not (np_ or avg_p):
            return "no power"
        if np_ and ftp and np_ / ftp >= 0.80:
            return "too hard for endurance (IF ≥ 0.80)"
        if np_ and avg_p and np_ / avg_p >= 1.10:
            return "uneven power (intervals)"
    else:
        if not a["km"]:
            return "no distance"
        if np_ and avg_p and np_ / avg_p >= 1.06:
            return "uneven effort (intervals)"
    return None


def _ef_points(sport: str) -> tuple[list[dict], dict]:
    """Steady aerobic sessions for the efficiency factor, plus why other sessions were left out.
    Runs/swims: metres per heartbeat (speed ÷ HR); rides: normalised power ÷ HR."""
    out, skipped = [], defaultdict(int)
    for a in acts():
        if a["sport"] != sport:
            continue
        why = _ef_check(a, sport)
        if why:
            if why not in ("no heart rate", "too short"):
                skipped[why] += 1
            continue
        e = _with_efficiency(a)
        if e["eff"]:
            out.append({k: e[k] for k in ("id", "date", "name", "minutes", "km", "avg_hr", "pace", "power", "decoupling", "eff")}
                       | {"indoor": (a.get("type") or "").lower() in INDOOR_TYPES})
    return out, dict(skipped)


INDOOR_TYPES = {"indoor_cycling", "virtualride", "virtual_ride", "treadmill_running", "indoor_running", "virtualrun", "virtual_run"}


def _ef_trend(pts: list[dict]) -> dict | None:
    """Average of the last 3 sessions vs the 3 up to six weeks before the last one (or the first 3, when the
    series is younger than that)."""
    if len(pts) < 6:
        return {"last": round(statistics.mean(p["eff"] for p in pts[-3:]), 3), "before": None, "pct": None, "since": None} if pts else None
    last = statistics.mean(p["eff"] for p in pts[-3:])
    cutoff = (date.fromisoformat(pts[-1]["date"]) - timedelta(days=42)).isoformat()
    early = [p for p in pts if p["date"] <= cutoff][-3:] or pts[:3]
    before = statistics.mean(p["eff"] for p in early)
    return {"last": round(last, 3), "before": round(before, 3), "pct": round((last / before - 1) * 100, 1), "since": early[-1]["date"]}


def _test_results(sport: str) -> list[dict]:
    """Tests done: workouts named like a protocol in library/tests.yaml (result from the coach report, else read from
    the workout), races and time trials for runs, plus results logged by hand in plans/tests.yaml."""
    protos = (cached(TESTS_LIB, read_yaml) or {}).get("tests", {}).get(sport, [])
    out = []
    for a in acts() if sport != "strength" else []:
        if a["sport"] != sport:
            continue
        name = a["name"] or ""
        proto = next((t for t in protos if t.get("match") and re.search(t["match"], name, re.I)), None)
        race = sport == "run" and re.search(r"race|time ?trial|timetrial|marathon|\bloop\b", name, re.I)
        if not proto and not race:
            continue
        rep = analyses().get(a["activity_id"]) or {}
        units = {"ftp": ("FTP", "W"), "lthr": ("LTHR", "bpm"), "six_min_power": ("6′ power", "W")}
        res = [{"label": units.get(k, (k.replace("_", " "), ""))[0], "value": f"{v} {units.get(k, ('', ''))[1]}".strip()}
               for k, v in (rep.get("result") or {}).items() if v is not None]
        if not res:
            if sport == "ride" and (a.get("np") or num(a["avg_power"])):
                res = [{"label": "NP", "value": f"{round(a.get('np') or num(a['avg_power']))} W"}]
            elif sport in ("run", "swim") and a["km"]:
                sec = round(a["minutes"] * 60)
                res = [{"label": "time", "value": (f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}")},
                       {"label": "distance", "value": f"{a['km']:.2f} km"}]
                if a["km"] >= 3:
                    p_ = a["minutes"] / a["km"]
                    res.append({"label": "pace", "value": f"{int(p_)}:{round(p_ % 1 * 60):02d}/km"})
            if proto and proto["id"].endswith("AEROBIC"):
                e = _with_efficiency(a)["eff"]
                res = [{"label": "EF", "value": e}] + ([{"label": "decoupling", "value": f"{a['decoupling']:.1f} %"}] if num(a.get("decoupling")) is not None else [])
            if num(a["avg_hr"]):
                res.append({"label": "avg HR", "value": f"{round(num(a['avg_hr']))} bpm"})
        out.append({"date": a["date"], "id": a["activity_id"], "name": clean_name(name),
                    "test": proto["name"] if proto else ("Half marathon" if 20.5 <= a["km"] <= 21.6 else "10 km" if 9.8 <= a["km"] <= 10.3
                                                         else "5 km" if 4.9 <= a["km"] <= 5.2 else "Race / time trial"), "results": res})
    for t in (cached(TESTS_LOG, read_yaml) or {}).get("tests", []) or []:
        if t.get("sport") == sport:
            proto = next((x for x in protos if x["id"] == t.get("test")), None)
            out.append({"date": str(t["date"]), "id": None, "name": t.get("notes") or "", "test": proto["name"] if proto else t.get("test"),
                        "results": [{"label": "result", "value": f"{t.get('value')} {t.get('unit') or ''}".strip()}]})
    if sport == "run":  # half marathons from all seasons, also when the activity isn't named as a race
        have = {x["date"] for x in out}
        out += [{"date": h["date"], "id": None, "name": h.get("place") or "", "test": "Half marathon",
                 "results": [{"label": "time", "value": h["time"]}]} for h in seasons()["half_marathons"] if h["date"] not in have]
    return sorted(out, key=lambda x: x["date"], reverse=True)


def progress() -> dict:
    """Per sport: efficiency factor over time, tests done, current thresholds and the tests you can do."""
    protos = (cached(TESTS_LIB, read_yaml) or {}).get("tests", {})
    icu_type = {"run": "Run", "ride": "Ride", "swim": "Swim"}
    lib = library()
    groups = defaultdict(list)
    for a in acts():
        w = workout_for(a)
        if w:
            groups[w].append(a)
    out = {}
    for sport in PROGRESS_SPORTS:
        st = settings_for(icu_type.get(sport, ""))
        thresholds = []
        if sport == "ride" and st.get("ftp"):
            thresholds.append({"label": "FTP", "value": f"{st['ftp']} W"})
        if st.get("lthr"):
            thresholds.append({"label": "LTHR", "value": f"{st['lthr']} bpm"})
        if st.get("max_hr"):
            thresholds.append({"label": "Max HR", "value": f"{st['max_hr']} bpm"})
        pts, skipped = _ef_points(sport) if sport != "strength" else ([], {})
        pts = pts[-80:]
        # indoor and outdoor differ (heat, no airflow, trainer power), so each gets its own trend
        trend = {"all": _ef_trend(pts), "indoor": _ef_trend([p for p in pts if p["indoor"]]),
                 "outdoor": _ef_trend([p for p in pts if not p["indoor"]])}
        repeats = []
        for wid, rows in groups.items():
            if len(rows) >= 2 and lib.get(wid, {}).get("sport") == sport:
                repeats.append({"id": wid, "name": lib[wid]["name"], "count": len(rows), "repeats": [_with_efficiency(a) for a in rows][-12:]})
        out[sport] = {"ef": {"unit": "W/beat" if sport == "ride" else "m/beat", "points": pts, "trend": trend, "skipped": skipped},
                      "tests": _test_results(sport), "thresholds": thresholds, "options": protos.get(sport, []),
                      "repeats": repeats, "sessions": sum(1 for a in acts() if a["sport"] == ("str" if sport == "strength" else sport))}
    return {"sports": out, "log_file": "plans/tests.yaml", "tests_file": "library/tests.yaml"}
