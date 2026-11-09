"""Activities: one row per activity in garmin_data/activities.csv, fetched incrementally (with a small
overlap to catch late edits), plus per-activity summary details."""

from __future__ import annotations

from datetime import date, timedelta

from .client import _r, ACTIVITIES_CSV, ACTIVITY_OVERLAP_DAYS, api_get, PAGE_SIZE, read_csv, ROOT, write_csv


ACTIVITY_COLUMNS = [
    "activity_id", "date", "start_local", "name", "type", "duration_min", "moving_min",
    "distance_km", "avg_speed_kmh", "pace_min_per_km", "gap_pace_min_per_km", "elev_gain_m",
    "avg_hr", "max_hr", "calories", "aerobic_te", "anaerobic_te", "te_label", "training_load",
    "avg_power", "norm_power", "avg_cadence", "avg_stride_cm", "avg_gct_ms", "avg_vert_osc_cm",
    "hr_z1_min", "hr_z2_min", "hr_z3_min", "hr_z4_min", "hr_z5_min",
    "moderate_im", "vigorous_im", "body_battery_delta", "rpe", "feel",
    "stamina_start", "stamina_end", "total_sets", "total_reps", "location", "details_ok",
]


def _pace(speed_ms):
    return round(1000 / speed_ms / 60, 2) if speed_ms else None


def project_activity(a: dict) -> dict:
    speed = a.get("averageSpeed")
    row = {
        "activity_id": a["activityId"],
        "date": a["startTimeLocal"][:10],
        "start_local": a["startTimeLocal"],
        "name": a.get("activityName"),
        "type": (a.get("activityType") or {}).get("typeKey"),
        "duration_min": _r((a.get("duration") or 0) / 60),
        "moving_min": _r((a.get("movingDuration") or 0) / 60),
        "distance_km": _r((a.get("distance") or 0) / 1000, 2),
        "avg_speed_kmh": _r(speed * 3.6, 2) if speed else None,
        "pace_min_per_km": _pace(speed),
        "gap_pace_min_per_km": _pace(a.get("avgGradeAdjustedSpeed")),
        "elev_gain_m": _r(a.get("elevationGain"), 0),
        "avg_hr": _r(a.get("averageHR"), 0),
        "max_hr": _r(a.get("maxHR"), 0),
        "calories": _r(a.get("calories"), 0),
        "aerobic_te": _r(a.get("aerobicTrainingEffect")),
        "anaerobic_te": _r(a.get("anaerobicTrainingEffect")),
        "te_label": a.get("trainingEffectLabel"),
        "training_load": _r(a.get("activityTrainingLoad")),
        "avg_power": _r(a.get("avgPower"), 0),
        "norm_power": _r(a.get("normPower"), 0),
        "avg_cadence": _r(a.get("averageRunningCadenceInStepsPerMinute")
                          or a.get("averageBikingCadenceInRevPerMinute"), 0),
        "avg_stride_cm": _r(a.get("avgStrideLength")),
        "avg_gct_ms": _r(a.get("avgGroundContactTime"), 0),
        "avg_vert_osc_cm": _r(a.get("avgVerticalOscillation")),
        "moderate_im": a.get("moderateIntensityMinutes"),
        "vigorous_im": a.get("vigorousIntensityMinutes"),
        "body_battery_delta": a.get("differenceBodyBattery"),
        "total_sets": a.get("totalSets"),
        "total_reps": a.get("totalReps"),
        "location": a.get("locationName"),
    }
    for z in range(1, 6):
        secs = a.get(f"hrTimeInZone_{z}")
        row[f"hr_z{z}_min"] = _r(secs / 60) if secs is not None else None
    return row


def _add_activity_details(row: dict) -> None:
    """RPE / feel / stamina live only on the per-activity endpoint (1 call per new activity)."""
    try:
        s = (api_get(f"/activity-service/activity/{row['activity_id']}") or {}).get("summaryDTO", {})
    except RuntimeError as e:
        print(f"  ! details for {row['activity_id']}: {e}")
        return
    rpe = s.get("directWorkoutRpe")
    row["rpe"] = rpe / 10 if rpe is not None else None  # Garmin stores 10-100
    row["feel"] = s.get("directWorkoutFeel")  # 0=very weak .. 100=very strong
    row["stamina_start"] = _r(s.get("beginPotentialStamina"), 0)
    row["stamina_end"] = _r(s.get("endPotentialStamina"), 0)
    row["details_ok"] = 1


def sync_activities() -> list[dict]:
    existing = {r["activity_id"]: r for r in read_csv(ACTIVITIES_CSV)}
    params = {"limit": PAGE_SIZE}
    if existing:
        last = max(r["date"] for r in existing.values())
        since = date.fromisoformat(last) - timedelta(days=ACTIVITY_OVERLAP_DAYS)
        params.update(startDate=since.isoformat(), endDate=date.today().isoformat())
        print(f"activities: fetching since {since}", flush=True)
    else:
        print("activities: first run, fetching full history")

    fetched, start = [], 0
    while True:
        page = api_get("/activitylist-service/activities/search/activities", {**params, "start": start}) or []
        fetched.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE

    new = 0
    for a in fetched:
        row = project_activity(a)
        aid = str(row["activity_id"])
        old = existing.get(aid)
        if old is None or recent(row["date"]):
            _add_activity_details(row)
        else:  # keep details we already have
            for k in ("rpe", "feel", "stamina_start", "stamina_end", "details_ok"):
                row[k] = old.get(k)
        new += old is None
        existing[aid] = row

    missing = [r for r in existing.values() if not r.get("details_ok")]
    if missing:
        print(f"activities: backfilling details for {len(missing)} activities", flush=True)
    for row in missing:
        _add_activity_details(row)

    rows = sorted(existing.values(), key=lambda r: r["start_local"])
    write_csv(ACTIVITIES_CSV, rows, ACTIVITY_COLUMNS)
    print(f"activities: {new} new, {len(rows)} total -> {ACTIVITIES_CSV.relative_to(ROOT)}")
    return rows


def recent(d: str) -> bool:
    return date.fromisoformat(d) >= date.today() - timedelta(days=ACTIVITY_OVERLAP_DAYS)
