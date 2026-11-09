"""Daily wellness and body data: daily.csv (resting HR, HRV, sleep, stress, body battery, steps), Garmin HR
zones, the derived training_load.csv, menstrual cycles (cycle.csv) and weight (weight.csv)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .client import _date_chunks, _r, ACTIVITIES_CSV, api_get, CYCLE_CSV, DAILY_CSV, DAILY_OVERLAP_DAYS, LOAD_CSV, read_csv, ROOT, WEIGHT_CSV, write_csv, ZONES_CSV


DAILY_COLUMNS = [
    "date", "resting_hr", "min_hr", "max_hr",
    "hrv_last_night", "hrv_weekly_avg", "hrv_status", "hrv_baseline_low", "hrv_baseline_high",
    "sleep_score", "sleep_h", "deep_h", "light_h", "rem_h", "awake_h", "sleep_avg_hr",
    "sleep_avg_stress", "sleep_resp", "sleep_spo2", "sleep_need_h",
    "body_battery_max", "body_battery_min", "body_battery_charged", "body_battery_drained",
    "stress_avg", "stress_max", "stress_qualifier",
    "steps", "active_kcal", "total_kcal", "moderate_im", "vigorous_im",
    "resp_avg", "spo2_avg",
]


def _h(secs):
    return round(secs / 3600, 2) if secs is not None else None


DAILY_CHUNK_DAYS = 14  # Garmin's sleep range endpoint sometimes hangs on bigger windows


def _fetch_daily(start: date, end: date) -> dict[str, dict]:
    rows: dict[str, dict] = defaultdict(dict)
    rng = {"startDate": start.isoformat(), "endDate": end.isoformat()}

    for x in (api_get("/usersummary-service/v2/dailysummaries", rng) or {}).get("data", []):
        hr, st, bb = x.get("heartRate", {}), x.get("stress", {}), x.get("bodyBattery", {})
        mv, cal, im = x.get("movement", {}), x.get("calories", {}), x.get("intensityMinutes", {})
        rows[x["calendarDate"]].update(
            resting_hr=hr.get("restingValue"), min_hr=hr.get("minValue"), max_hr=hr.get("maxValue"),
            body_battery_max=bb.get("maxValue"), body_battery_min=bb.get("minValue"),
            body_battery_charged=bb.get("chargedValue"), body_battery_drained=bb.get("drainedValue"),
            stress_avg=st.get("avgLevel"), stress_max=st.get("maxLevel"), stress_qualifier=st.get("qualifier"),
            steps=(mv.get("steps") or {}).get("value"), active_kcal=cal.get("burnedActive"),
            total_kcal=cal.get("burnedTotal"), moderate_im=im.get("moderate"), vigorous_im=im.get("vigorous"),
            resp_avg=(x.get("respiration") or {}).get("avgValue"),
            spo2_avg=(x.get("pulseOx") or {}).get("avgValue"),
        )

    for x in api_get("/sleep-service/sleep/dailySleepSummariesByDate", rng) or []:
        need = x.get("sleepNeed") or {}
        rows[x["calendarDate"]].update(
            sleep_score=((x.get("sleepScores") or {}).get("overall") or {}).get("value"),
            sleep_h=_h(x.get("sleepTimeSeconds")), deep_h=_h(x.get("deepSleepSeconds")),
            light_h=_h(x.get("lightSleepSeconds")), rem_h=_h(x.get("remSleepSeconds")),
            awake_h=_h(x.get("awakeSleepSeconds")), sleep_avg_hr=x.get("avgHeartRate"),
            sleep_avg_stress=x.get("avgSleepStress"), sleep_resp=x.get("averageRespirationValue"),
            sleep_spo2=x.get("averageSpO2Value"),
            sleep_need_h=round(need["actual"] / 60, 2) if need.get("actual") else None,
        )

    d = api_get(f"/hrv-service/hrv/daily/{start.isoformat()}/{end.isoformat()}") or {}
    for x in d.get("hrvSummaries", []):
        b = x.get("baseline") or {}
        rows[x["calendarDate"]].update(
            hrv_last_night=x.get("lastNightAvg"), hrv_weekly_avg=x.get("weeklyAvg"),
            hrv_status=x.get("status"), hrv_baseline_low=b.get("balancedLow"),
            hrv_baseline_high=b.get("balancedUpper"),
        )
    return rows


def _save_daily(existing: dict[str, dict]) -> list[dict]:
    # drop empty days (before the watch was worn)
    rows = [r for r in sorted(existing.values(), key=lambda r: r["date"])
            if any(r.get(k) not in (None, "") for k in DAILY_COLUMNS[1:])]
    write_csv(DAILY_CSV, rows, DAILY_COLUMNS)
    return rows


def sync_daily(activities: list[dict] | None = None) -> list[dict]:
    existing = {r["date"]: r for r in read_csv(DAILY_CSV)}
    today = date.today()
    if existing:
        start = date.fromisoformat(max(existing)) - timedelta(days=DAILY_OVERLAP_DAYS)
    else:
        acts = activities if activities is not None else read_csv(ACTIVITIES_CSV)
        start = date.fromisoformat(min(r["date"] for r in acts)) if acts else today - timedelta(days=365)
        print(f"daily: first run, fetching from {start}", flush=True)
    print(f"daily: fetching {start} .. {today}", flush=True)

    rows = []
    for s, e in _date_chunks(start, today, DAILY_CHUNK_DAYS):
        for d, vals in _fetch_daily(s, e).items():
            if not d:  # Garmin occasionally returns a record without calendarDate
                continue
            existing.setdefault(d, {"date": d}).update(vals)
        rows = _save_daily(existing)  # save per chunk so an interrupted first run resumes
        print(f"  daily: up to {e}", flush=True)

    print(f"daily: {len(rows)} days -> {DAILY_CSV.relative_to(ROOT)}")
    return rows


ZONE_COLUMNS = [
    "synced", "sport", "method", "resting_hr", "lthr", "max_hr",
    "z1_floor", "z2_floor", "z3_floor", "z4_floor", "z5_floor",
]


def sync_zones() -> None:
    """One call per run. Appends a row per sport only when its zone settings changed."""
    history = read_csv(ZONES_CSV)
    latest = {r["sport"]: r for r in history}  # rows are chronological, so last one wins
    added = 0
    for z in api_get("/biometric-service/heartRateZones/v2") or []:
        row = {
            "synced": date.today().isoformat(),
            "sport": z.get("sport"),
            "method": z.get("trainingMethod"),
            "resting_hr": z.get("restingHeartRateUsed"),
            "lthr": z.get("lactateThresholdHeartRateUsed"),
            "max_hr": z.get("maxHeartRateUsed"),
            **{f"z{i}_floor": z.get(f"zone{i}Floor") for i in range(1, 6)},
        }
        prev = latest.get(row["sport"])
        # resting HR auto-updates daily; don't log a new row just for that
        keys = [k for k in ZONE_COLUMNS if k not in ("synced", "resting_hr")]
        if prev is None or any(str(prev.get(k) or "") != str(row[k] or "") for k in keys):
            history.append(row)
            added += 1
    write_csv(ZONES_CSV, history, ZONE_COLUMNS)
    print(f"hr zones: {added} changed -> {ZONES_CSV.relative_to(ROOT)}")


LOAD_COLUMNS = [
    "date", "sessions", "minutes", "load", "acute_load_7d", "chronic_load_28d", "acwr",
    "hr_z1_min", "hr_z2_min", "hr_z3_min", "hr_z4_min", "hr_z5_min",
    "run_km", "bike_km", "row_km", "strength_min",
    "resting_hr", "hrv_last_night", "hrv_status", "sleep_score", "sleep_h", "body_battery_max", "stress_avg",
]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_training_load(activities: list[dict] | None = None, daily: list[dict] | None = None) -> None:
    """Pure local computation. Garmin's own training status/readiness are not exposed by the
    Personal API, so acute (7d mean) and chronic (28d mean) load + ACWR are computed here
    from per-activity Garmin training load (EPOC)."""
    acts = activities if activities is not None else read_csv(ACTIVITIES_CSV)
    days = {r["date"]: r for r in (daily if daily is not None else read_csv(DAILY_CSV))}
    if not acts:
        return

    per_day: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for a in acts:
        p, t = per_day[a["date"]], a["type"] or ""
        p["sessions"] += 1
        p["minutes"] += _f(a["duration_min"])
        p["load"] += _f(a["training_load"])
        for z in range(1, 6):
            p[f"hr_z{z}_min"] += _f(a[f"hr_z{z}_min"])
        if "running" in t:
            p["run_km"] += _f(a["distance_km"])
        elif "cycling" in t or "biking" in t:
            p["bike_km"] += _f(a["distance_km"])
        elif "rowing" in t:
            p["row_km"] += _f(a["distance_km"])
        elif "strength" in t:
            p["strength_min"] += _f(a["duration_min"])

    first = date.fromisoformat(min(per_day))
    last = max(date.today(), date.fromisoformat(max(per_day)))
    loads, rows = [], []
    d = first
    while d <= last:
        key = d.isoformat()
        p = per_day.get(key, {})
        loads.append(p.get("load", 0.0))
        acute = sum(loads[-7:]) / 7
        chronic = sum(loads[-28:]) / 28
        row = {"date": key, **{k: _r(v) for k, v in p.items()}}
        row.setdefault("sessions", 0)
        row.update(acute_load_7d=_r(acute), chronic_load_28d=_r(chronic),
                   acwr=_r(acute / chronic, 2) if chronic and len(loads) >= 28 else None)
        w = days.get(key, {})
        for k in ("resting_hr", "hrv_last_night", "hrv_status", "sleep_score", "sleep_h",
                  "body_battery_max", "stress_avg"):
            row[k] = w.get(k)
        rows.append(row)
        d += timedelta(days=1)

    write_csv(LOAD_CSV, rows, LOAD_COLUMNS)
    print(f"training load: {len(rows)} days -> {LOAD_CSV.relative_to(ROOT)}")


CYCLE_COLUMNS = ["start", "end", "cycle_length", "period_length", "fertile_start", "fertile_length", "cycle_type", "ongoing"]


def sync_cycle() -> list[dict]:
    """Menstrual cycles from Garmin's cycle tracking, one row per cycle. Garmin's day view gives the cycle a day
    belongs to; walking back from today (day before each cycle start) finds earlier cycles until a known one."""
    known = {r["start"]: r for r in read_csv(CYCLE_CSV)}
    found, d = {}, date.today()
    for _ in range(40):
        s = (api_get(f"/periodichealth-service/menstrualcycle/dayview/{d.isoformat()}") or {}).get("daySummary")
        if not s or not s.get("startDate"):
            break
        start = s["startDate"]
        found[start] = {"start": start, "period_length": s.get("periodLength"), "fertile_start": s.get("fertileWindowStart"),
                        "fertile_length": s.get("lengthOfFertileWindow"), "cycle_type": s.get("cycleType"),
                        "predicted_length": s.get("predictedCycleLength")}
        if start in known and len(found) > 1:  # reached cycles we already have (the current one is always refreshed)
            break
        d = date.fromisoformat(start) - timedelta(days=1)
    rows = {**known, **found}
    starts = sorted(rows)
    out = []
    for i, st in enumerate(starts):
        r = dict(rows[st])
        nxt = starts[i + 1] if i + 1 < len(starts) else None
        r["ongoing"] = "" if nxt else "yes"
        r["cycle_length"] = (date.fromisoformat(nxt) - date.fromisoformat(st)).days if nxt else (r.get("predicted_length") or r.get("cycle_length"))
        r["end"] = (date.fromisoformat(nxt) - timedelta(days=1)).isoformat() if nxt else ""
        out.append({k: r.get(k) for k in CYCLE_COLUMNS})
    if out:
        write_csv(CYCLE_CSV, out, CYCLE_COLUMNS)
    print(f"cycle: {len(out)} cycles -> {CYCLE_CSV.relative_to(ROOT)}" if out else "cycle: no cycle tracking data")
    return out


WEIGHT_COLUMNS = ["date", "weight_kg", "body_fat_pct", "muscle_kg", "source"]


def sync_weight() -> list[dict]:
    """Daily weight (and body fat from the Index scale) from Garmin, appended incrementally."""
    rows = {r["date"]: r for r in read_csv(WEIGHT_CSV)}
    start = (max(rows) if rows else (date.today() - timedelta(days=730)).isoformat())
    start_d = date.fromisoformat(start) - timedelta(days=DAILY_OVERLAP_DAYS)
    for s0, s1 in _date_chunks(start_d, date.today(), 90):
        d = api_get(f"/weight-service/weight/range/{s0.isoformat()}/{s1.isoformat()}", {"includeAll": "true"}) or {}
        for x in d.get("dailyWeightSummaries", []):
            w = x.get("latestWeight") or {}
            if w.get("weight"):
                rows[x["summaryDate"]] = {"date": x["summaryDate"], "weight_kg": round(w["weight"] / 1000, 2),
                                          "body_fat_pct": w.get("bodyFat"), "source": w.get("sourceType"),
                                          "muscle_kg": round(w["muscleMass"] / 1000, 1) if w.get("muscleMass") else None}
    out = [rows[k] for k in sorted(rows)]
    if out:
        write_csv(WEIGHT_CSV, out, WEIGHT_COLUMNS)
    print(f"weight: {len(out)} days -> {WEIGHT_CSV.relative_to(ROOT)}")
    return out
