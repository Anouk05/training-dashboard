"""Dashboard API. Run: .venv/bin/uvicorn app.backend.main:app --port 8765 (from the Sport folder)."""

from __future__ import annotations

import threading
from datetime import date, datetime

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from . import activity, atp, body, nutrition, progress, season, strength, week, workouts

# sync clients in the project root (store puts it on sys.path)
import garmin_sync
import intervals_sync
import notion_sync

app = FastAPI(title="Pulse")
_last_sync: dict = {"at": None, "ok": None}


def _warm() -> None:
    """Background warm-up: build the data caches and fetch recent workout details from Garmin."""
    try:
        week.today(), season.season(), season.seasons()
        activity.prefetch_details()
    except Exception as e:  # never block the API on this
        print(f"warm-up skipped: {e}")


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_warm, daemon=True).start()


@app.get("/api/today")
def get_today():
    return week.today() | {"sync": _last_sync}


@app.get("/api/week")
def get_week(start: date | None = None):
    return week.week(start)


@app.get("/api/fitness")
def get_fitness(days: int = 180):
    return body.fitness(days)


@app.get("/api/season")
def get_season():
    return season.season()


@app.get("/api/atp")
def get_atp():
    return atp.atp()


class AtpEdit(BaseModel):
    starts: list[str]   # Mondays of the weeks to change
    changes: dict       # any of period, volume, weights, swim, bike, run, note


@app.post("/api/atp/weeks")
def atp_edit(e: AtpEdit):
    try:
        return atp.set_atp_weeks(e.starts, dict(e.changes))
    except ValueError as err:
        raise HTTPException(400, str(err))


@app.get("/api/fuel")
def fuel_overview():
    return nutrition.overview()


@app.get("/api/fuel/day/{d}")
def fuel_day(d: str):
    return nutrition.day(d)


class Meal(BaseModel):
    id: str | None = None
    slot: str = "snack"
    time: str | None = None
    text: str
    kcal: float | None = None
    carbs: float | None = None
    protein: float | None = None
    fat: float | None = None


@app.post("/api/fuel/day/{d}/meal")
def fuel_meal(d: str, m: Meal):
    return nutrition.save_meal(d, m.model_dump())


@app.delete("/api/fuel/day/{d}/meal/{mid}")
def fuel_meal_delete(d: str, mid: str):
    return nutrition.delete_meal(d, mid)


@app.get("/api/activity/{aid}/fuel")
def fuel_check(aid: str):
    try:
        return nutrition.fuel_check(aid)
    except ValueError as err:
        raise HTTPException(404, str(err))


class FuelLog(BaseModel):
    before: dict = {}
    during: dict = {}
    other_g: float | None = None
    after: dict = {}
    notes: str = ""


@app.post("/api/activity/{aid}/fuel")
def fuel_check_save(aid: str, f: FuelLog):
    return nutrition.set_fuel_check(aid, f.model_dump())


@app.get("/api/seasons")
def get_seasons():
    return season.seasons()


@app.get("/api/activities")
def get_activities(limit: int = 60, sport: str | None = None):
    return activity.activity_list(limit, sport)


@app.get("/api/activity/{aid}")
def get_activity(aid: str):
    a = activity.activity(aid)
    if not a:
        raise HTTPException(404)
    return a


@app.get("/api/progress")
def get_progress():
    return progress.progress()


@app.get("/api/strength")
def get_strength():
    return strength.overview()


@app.get("/api/strength/day/{d}")
def get_strength_day(d: str):
    return strength.day(d)


@app.get("/api/recovery")
def get_recovery(days: int = 365):
    return body.recovery(days)


@app.get("/api/library")
def get_library():
    return activity.library_page()


class Move(BaseModel):
    week_start: date
    to: date
    event_id: int | None = None  # intervals.icu planned workout
    index: int | None = None     # fallback: session line in a plans/weeks YAML file


@app.post("/api/week/move")
async def move(m: Move):
    try:
        if m.event_id is not None:
            await run_in_threadpool(workouts.move_event, m.event_id, m.to)
        else:
            workouts.move_session(m.week_start, m.index, m.to)
    except (FileNotFoundError, IndexError):
        raise HTTPException(404)
    except RuntimeError as e:  # intervals.icu refused the change
        raise HTTPException(502, str(e)[:300])
    return week.week(m.week_start)


class WorkoutEdit(BaseModel):
    week_start: date
    name: str | None = None
    description: str | None = None
    type: str | None = None   # intervals.icu sport: Run, Ride, Swim, WeightTraining, …
    day: date | None = None   # move to this date


@app.post("/api/event/{event_id}")
async def edit_event(event_id: int, e: WorkoutEdit):
    changes = e.model_dump(exclude={"week_start", "day"}, exclude_none=True)
    if e.day:
        changes["date"] = e.day.isoformat()
    try:
        await run_in_threadpool(workouts.update_event, event_id, changes)
    except (RuntimeError, ValueError) as err:
        raise HTTPException(502, str(err)[:300])
    return week.week(e.week_start)


class WorkoutTime(BaseModel):
    week_start: date
    time: str | None = None  # "07:30"; None = just planned for the day


@app.post("/api/event/{event_id}/time")
async def set_event_time(event_id: int, t: WorkoutTime):
    try:
        await run_in_threadpool(workouts.set_time, event_id, t.time or None)
    except ValueError as err:
        raise HTTPException(422, str(err))
    except RuntimeError as err:
        raise HTTPException(502, str(err)[:300])
    return week.week(t.week_start)


class WorkoutNew(BaseModel):
    week_start: date
    day: date
    name: str
    type: str = "Run"
    description: str = ""


@app.post("/api/event")
async def create_event(n: WorkoutNew):
    if not n.name.strip():
        raise HTTPException(422, "a workout needs a name")
    try:
        await run_in_threadpool(workouts.create_event, n.day, n.name.strip(), n.type, n.description)
    except RuntimeError as err:
        raise HTTPException(502, str(err)[:300])
    return week.week(n.week_start)


@app.delete("/api/event/{event_id}")
async def delete_event(event_id: int, week_start: date):
    try:
        await run_in_threadpool(workouts.delete_event, event_id)
    except RuntimeError as err:
        raise HTTPException(502, str(err)[:300])
    return week.week(week_start)


class Notes(BaseModel):
    notes: str


@app.post("/api/activity/{aid}/notes")
async def save_notes(aid: str, n: Notes):
    try:
        await run_in_threadpool(workouts.set_notes, aid, n.notes.strip())
    except ValueError as err:
        raise HTTPException(409, str(err))
    except RuntimeError as err:
        raise HTTPException(502, str(err)[:300])
    return activity.activity(aid)


class Preview(BaseModel):
    description: str
    sport: str = "other"


@app.post("/api/workout/preview")
def preview(p: Preview):
    return workouts.preview_workout(p.description, p.sport)


@app.post("/api/sync")
async def sync():
    try:
        await run_in_threadpool(garmin_sync.sync)
        await run_in_threadpool(intervals_sync.sync)
        try:
            await run_in_threadpool(notion_sync.sync)  # strength log; optional, never blocks the sync
            await run_in_threadpool(lambda: notion_sync.push_plan(strength.notion_plan()))  # planned gym sessions + targets
        except Exception as e:
            print(f"notion: skipped ({e})")
        _last_sync.update(at=datetime.now().isoformat(timespec="minutes"), ok=True)
        threading.Thread(target=_warm, daemon=True).start()  # new workouts: fetch their details right away
    except Exception as e:  # surface the reason in the UI
        _last_sync.update(at=datetime.now().isoformat(timespec="minutes"), ok=False, error=str(e)[:200])
    return _last_sync
