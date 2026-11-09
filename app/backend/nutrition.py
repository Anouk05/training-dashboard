"""Nutrition: fuel targets per workout, the quick fuel check per completed workout, the food log, and the daily
intake check (kcal, carbs and protein per kg, energy availability). Body weight comes from Garmin (Index scale).

Storage (all local, in nutrition/):
  fuel.json            {activity id: {before, during, after, carbs_g, notes}}  · carbs also go to intervals.icu
  intake/<date>.json   {meals: [{id, slot, time, text, kcal, carbs, protein, fat, source}]}
  foods.yaml           during-workout items with their carbs, for the quick check
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

from datetime import datetime

from .store import ROOT, num
from . import sources, store, workouts

# sync clients in the project root (store puts it on sys.path)
import intervals_sync

DIR = ROOT / "nutrition"
FUEL = DIR / "fuel.json"
INTAKE = DIR / "intake"
FOODS = DIR / "foods.yaml"


# --------------------------------------------------------------------------- body

def body() -> dict:
    """Latest weight and body fat from Garmin; fat-free mass for energy availability."""
    rows = store.cached(store.GARMIN / "weight.csv", store.read_csv) or []
    if not rows:
        return {"weight": None}
    last = rows[-1]
    w, bf = num(last["weight_kg"]), num(last.get("body_fat_pct"))
    recent = [num(r["weight_kg"]) for r in rows if r["date"] >= (date.today() - timedelta(days=30)).isoformat() and num(r["weight_kg"])]
    return {"weight": w, "body_fat": bf, "ffm": round(w * (1 - bf / 100), 1) if w and bf else None, "date": last["date"],
            "avg30": round(sum(recent) / len(recent), 1) if recent else None, "n30": len(recent)}


def _kg() -> float:
    return body().get("weight") or 60.0


# --------------------------------------------------------------------------- fuel targets

def _hard(abilities: list[str], load: float, minutes: float) -> bool:
    return bool(set(abilities) & {"ME", "AC", "SP", "T"}) or (minutes and load / (minutes / 60) > 75)


def fuel_target(w: dict, next_hours: float | None = None) -> dict:
    """Before / during / after targets for one workout (planned or done), from duration, intensity and sport.
    Sports-nutrition guidelines (ACSM/IOC): carbs during scale with duration; recovery matters most after hard or
    long sessions, or when the next session is within ~24 h."""
    kg, mins, sport = _kg(), w.get("minutes") or 0, w.get("sport")
    ab = w.get("abilities") or []
    hard = _hard(ab, w.get("load") or 0, mins)
    long_ = mins >= 90
    if sport == "str":
        return {"kind": "strength", "before": "Normal meal 2–3 h before, or a small snack (20–30 g carbs) 1 h before.",
                "during": {"rate": 0, "total": 0, "text": "Water is enough."},
                "after": {"protein": round(0.3 * kg), "carbs": 0, "text": f"About {round(0.3 * kg)} g protein within 1–2 h (e.g. yoghurt or quark with fruit)."}}
    # before
    if long_ or hard:
        pre = round(1.5 * kg / 10) * 10
        before = f"Meal with ~{pre} g carbs 2–3 h before (e.g. oats or bread with banana), or a 30–40 g carb snack 1 h before."
    elif mins >= 45:
        before = "Normal meal within ~3 h, or a small snack (20–30 g carbs) if it's been longer."
    else:
        before = "Nothing special; a small snack if you're hungry."
    # during: g carbs per hour
    rate = 0 if (mins < 75 and not hard) or mins < 45 else 30 if mins < 90 else 60 if mins <= 180 else 75
    total = round(rate * mins / 60 / 5) * 5
    during = {"rate": rate, "total": total,
              "text": "Water is enough." if not rate else f"{rate} g carbs per hour, ~{total} g in total; start after 20–30′"
              + (" and drink 400–800 ml per hour." if mins >= 60 else ".")}
    # after
    soon = next_hours is not None and next_hours <= 8  # quick refuelling only matters with < ~8 h between sessions
    if hard or long_ or soon:
        c, p = round(1.0 * kg / 5) * 5, round(0.3 * kg)
        after = {"protein": p, "carbs": c, "text": f"Within 1 h: ~{c} g carbs and ~{p} g protein (e.g. a meal, or yoghurt + muesli + fruit)."
                 + (f" Your next session is in {next_hours:.0f} h, so refuel quickly." if soon else "")}
    else:
        after = {"protein": round(0.3 * kg), "carbs": 0, "text": f"Your next normal meal, with ~{round(0.3 * kg)} g protein."}
    return {"kind": "hard" if hard else "long" if long_ else "easy", "before": before, "during": during, "after": after}


def _next_session_hours(start_iso: str, minutes: float) -> float | None:
    """Hours from the end of this session to the next one: a later recorded workout, or a planned one on a later day
    (planned workouts have no time of day, so they count as starting at 12:00)."""
    end = datetime.fromisoformat(start_iso[:19]) + timedelta(minutes=minutes)
    done = [a["start"] for a in sources.acts() if a["start"] > end - timedelta(minutes=5) and a["sport"] != "str"]
    planned = [datetime.fromisoformat(e["start_date_local"][:10] + "T12:00:00") for e in sources.events()
               if e["category"] == "WORKOUT" and e["start_date_local"][:10] > start_iso[:10]]
    nxt = [t for t in done + planned if t > end - timedelta(minutes=5)]
    return round(max(0.0, (min(nxt) - end).total_seconds() / 3600), 1) if nxt else None


def today_plan(day: date | None = None) -> list[dict]:
    """Fuel targets for the planned workouts of a day."""
    day = day or date.today()
    out = []
    done = [a for a in sources.acts() if a["start"].date() == day]
    used = set()
    for e in sources.calendar(day, day, ("WORKOUT",)):
        p = workouts.planned_from_event(e)
        a = next((a for a in done if str(a.get("paired_event_id") or "") == str(e["id"])), None)
        if a:
            used.add(a["activity_id"])
        nh = _next_session_hours(e["start_date_local"], p["minutes"])
        c = _done_check(a) if a else {}
        out.append({"name": p["name"], "sport": p["sport"], "minutes": p["minutes"], "load": p["load"], "abilities": p["abilities"],
                    "target": c.pop("check_target", None) or fuel_target(p, nh)} | c)
    for a in done:  # unplanned sessions done today
        if a["activity_id"] not in used and a["sport"] != "str":
            c = _done_check(a)
            out.append({"name": store.clean_name(a["name"]), "sport": a["sport"], "minutes": round(a["minutes"]), "load": a["load"],
                        "abilities": [], "target": c.pop("check_target")} | c)
    return out


def _done_check(a: dict) -> dict:
    """The fuel check of a completed workout, for the Fuel today cards."""
    f = fuel_check(a["activity_id"])
    return {"done_id": a["activity_id"], "check": f["log"], "verdict": f["verdict"], "carbs_g": (f["log"] or {}).get("carbs_g"),
            "check_target": f["target"]}


# --------------------------------------------------------------------------- quick fuel check

def _read_json(p, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def foods() -> list[dict]:
    return (store.cached(FOODS, store.read_yaml) or {}).get("during", [])


def fuel_check(aid: str) -> dict:
    a = next((x for x in sources.acts() if x["activity_id"] == aid), None)
    if not a:
        raise ValueError("unknown activity")
    s = workouts.act_summary(a)
    ev = next((e for e in sources.events() if a.get("paired_event_id") and str(e["id"]) == str(a["paired_event_id"])), None)
    s["abilities"] = workouts.abilities_for(ev) if ev else []
    nh = _next_session_hours(a["start_local"], a["minutes"])
    log = _read_json(FUEL, {}).get(aid)
    t = fuel_target(s, nh)
    return {"target": t, "log": log, "foods": foods(), "verdict": _verdict(t, log, a["minutes"])}


def _verdict(t: dict, log: dict | None, minutes: float) -> dict | None:
    """Compare a fuel check with the target. Fasted training is never "on target" for sessions of 45′ or more:
    with your history of low energy availability, fuelling before training matters even on easy days."""
    if not log:
        return None
    rate_t, got = t["during"]["rate"], log.get("carbs_g") or 0
    rate = got / (minutes / 60) if minutes else 0
    during = "ok" if not rate_t or rate >= rate_t * 0.75 else "low"
    during_text = f"{round(rate)} g/h vs {rate_t} g/h" if rate_t else "no carbs needed during"
    b = log.get("before") or {}
    timing, size = b.get("timing"), b.get("size")
    if not timing:
        before, before_text = "low", "not filled in"
    elif t["kind"] == "strength" or minutes < 45:
        before, before_text = ("ok", "fine for a short or strength session") if timing != "fasted" or minutes < 30 else ("low", "trained fasted")
    elif timing == "fasted":
        before, before_text = "low", "trained fasted; eat something first, even before easy sessions"
    elif timing == ">3h":
        before, before_text = "low", "more than 3 h since you ate; add a 20–30 g carb snack 30–60′ before"
    elif t["kind"] in ("hard", "long") and timing == "1-3h" and size != "meal":
        before, before_text = "low", "only a snack 1–3 h before a long or hard session; make it a meal"
    else:
        before, before_text = "ok", "fuelled before"
    k = (log.get("after") or {}).get("kind")
    if t["after"]["carbs"]:
        after, after_text = ("ok", "recovery within the hour") if k in ("meal", "snack") else ("low", "no recovery food within the hour")
    else:
        after, after_text = ("ok", "next meal is enough") if k and k != "none" else ("low", "nothing eaten after") if k == "none" else ("low", "not filled in")
    return {"before": before, "before_text": before_text, "during": during, "during_text": during_text,
            "after": after, "after_text": after_text, "ok": all(x == "ok" for x in (before, during, after))}


def set_fuel_check(aid: str, log: dict) -> dict:
    """Save the quick check; the carbs taken during also go to intervals.icu (activity field carbs_ingested)."""
    items = {f["id"]: f for f in foods()}
    carbs = sum((items.get(k, {}).get("carbs") or 0) * (n or 0) for k, n in (log.get("during") or {}).items()) + (num(log.get("other_g")) or 0)
    log = {**log, "carbs_g": round(carbs)}
    allf = _read_json(FUEL, {})
    allf[aid] = log
    DIR.mkdir(exist_ok=True)
    FUEL.write_text(json.dumps(allf, indent=1, ensure_ascii=False))
    a = next((x for x in sources.acts() if x["activity_id"] == aid), None)
    if a and a.get("icu_id"):
        try:
            cur = intervals_sync.get(f"/activity/{a['icu_id']}")
            # a PUT without the name resets it to the default, so always send it along
            intervals_sync.request("PUT", f"/activity/{a['icu_id']}", {"name": cur.get("name"), "carbs_ingested": log["carbs_g"]})
        except Exception as err:
            return fuel_check(aid) | {"sync_error": str(err)}
    return fuel_check(aid)


# --------------------------------------------------------------------------- food log and daily check

def _day_file(d: str):
    return INTAKE / f"{d}.json"


def day(d: str) -> dict:
    """The food log of a day with totals against targets for that day's training."""
    meals = _read_json(_day_file(d), {"meals": []})["meals"]
    kg, b = _kg(), body()
    dd = date.fromisoformat(d)
    done = [a for a in sources.acts() if a["start"].date() == dd]
    planned = [] if done else [workouts.planned_from_event(e) for e in sources.calendar(dd, dd, ("WORKOUT",))]
    hours = sum(a["minutes"] for a in done) / 60 or sum(p["minutes"] for p in planned) / 60
    ex_kcal = sum(num(a.get("calories")) or 0 for a in done)
    if not done and planned:  # estimate a planned day's burn from load-free rule of thumb: ~8 kcal/min endurance, 5 strength
        ex_kcal = sum(p["minutes"] * (5 if p["sport"] == "str" else 8) for p in planned)
    hard = any(_hard(workouts.abilities_for(e), workouts.planned_from_event(e)["load"], workouts.planned_from_event(e)["minutes"])
               for e in sources.calendar(dd, dd, ("WORKOUT",)))
    # daily carbs: 3–5 g/kg light, 5–7 moderate (≈1 h/day), 6–10 high (1–3 h); protein 1.6–2.0 g/kg
    carb_lo, carb_hi = (3, 5) if hours < 0.75 else (5, 7) if hours < 1.75 and not hard else (6, 8)
    tot = {k: round(sum(num(m.get(k)) or 0 for m in meals)) for k in ("kcal", "carbs", "protein", "fat")}
    missing = sum(1 for m in meals if num(m.get("kcal")) is None)
    ea = round((tot["kcal"] - ex_kcal) / b["ffm"]) if b.get("ffm") and tot["kcal"] and not missing else None
    return {"date": d, "meals": meals, "totals": tot, "to_estimate": missing,
            "training": {"hours": round(hours, 1), "exercise_kcal": round(ex_kcal), "hard": hard, "planned": bool(planned and not done)},
            "targets": {"carbs": [round(carb_lo * kg), round(carb_hi * kg)], "carbs_gkg": [carb_lo, carb_hi],
                        "protein": [round(1.6 * kg), round(2.0 * kg)], "ea_ok": 45, "ea_low": 30},
            "per_kg": {"carbs": round(tot["carbs"] / kg, 1) if tot["carbs"] else None, "protein": round(tot["protein"] / kg, 1) if tot["protein"] else None},
            "ea": ea, "body": b}


def save_meal(d: str, meal: dict) -> dict:
    f = _day_file(d)
    cur = _read_json(f, {"meals": []})
    meal = {k: meal.get(k) for k in ("id", "slot", "time", "text", "kcal", "carbs", "protein", "fat")}
    for k in ("kcal", "carbs", "protein", "fat"):
        meal[k] = num(meal[k]) if meal[k] not in (None, "") else None
    meal["source"] = "you" if meal["kcal"] is not None else None  # Claude fills the rest and marks it "estimate"
    if not meal.get("id"):
        meal["id"] = uuid.uuid4().hex[:8]
        cur["meals"].append(meal)
    else:
        cur["meals"] = [meal if m["id"] == meal["id"] else m for m in cur["meals"]]
    cur["meals"].sort(key=lambda m: m.get("time") or "99")
    INTAKE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, indent=1, ensure_ascii=False))
    return day(d)


def delete_meal(d: str, mid: str) -> dict:
    f = _day_file(d)
    cur = _read_json(f, {"meals": []})
    cur["meals"] = [m for m in cur["meals"] if m["id"] != mid]
    f.write_text(json.dumps(cur, indent=1, ensure_ascii=False))
    return day(d)


def overview(days: int = 7) -> dict:
    """Last days: logged intake vs targets, and how many workouts were fuelled to target."""
    t = date.today()
    out = []
    for i in range(days - 1, -1, -1):
        dd = day((t - timedelta(days=i)).isoformat())
        out.append({k: v for k, v in dd.items() if k not in ("meals", "body")} | {"n_meals": len(dd["meals"])})
    fl = _read_json(FUEL, {})
    recent = [a for a in sources.acts() if a["start"].date() >= t - timedelta(days=days - 1) and a["sport"] != "str"]
    checked = [a for a in recent if a["activity_id"] in fl]
    on = 0
    for a in checked:
        v = fuel_check(a["activity_id"])["verdict"]
        on += bool(v and v["ok"])
    return {"days": out, "workouts": len(recent), "checked": len(checked), "on_target": on, "body": body(), "today_plan": today_plan()}
