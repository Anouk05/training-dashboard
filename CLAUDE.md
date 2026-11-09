# Sport: training data, plans and the Pulse dashboard

## Layout
- `garmin_sync.py`: incremental Garmin Personal API sync, writes to `garmin_data/` (`python3 garmin_sync.py`). The code is in `garmin/`: `client.py` (auth, HTTP, CSV helpers), `activities.py`, `wellness.py` (daily, zones, training load, cycle, weight).
- `intervals_sync.py`: incremental intervals.icu sync, writes to `intervals_data/` (activities with load/RPE/notes, wellness with CTL/ATL, the full calendar in `events.json`). It also has `move_event()` for rescheduling planned workouts. The dashboard's Sync button runs both scripts.
- `garmin_data/`: generated CSVs (`activities`, `daily`, `training_load`, `hr_zones`, `cycle` = menstrual cycles from Garmin cycle tracking, `weight`) plus `details/` (per-activity samples cache). Never edit by hand.
- **The intervals.icu calendar is the source of truth for the plan**: season start, races (RACE_A/B/C), planned workouts (synced to the watch and Edge) and notes (weekly notes act as phase labels, e.g. "Build - week 2"). To plan, write workouts into intervals.icu, not into local files.
- `plans/seasons.yaml`: past seasons (windows, goals, extra results). `plans/weeks/` is only a fallback when there's no calendar.
- `library/workouts.yaml`: standard workouts with stable IDs (`RUN-THR-2k`, …); `match` regexes link Garmin activities to them.
- `coach/rules.yaml`: hard rules checked by the dashboard. `coach/principles.md`: judgment calls; read both before planning or analysing.
- Skills in `.claude/skills/`: `plan-season` (annual plan, with the weekly volume tables), `plan-week` (weekly routine, with the daily volume tables), `analyze-workout`, `estimate-food`.
- `reports/coach/<date>.md`: optional daily coach note; when present, the Today page shows it instead of the auto-check.
- `reports/workouts/<date>-<activity id>.md`: coach report per completed workout, written by the `analyze-workout` skill (`.claude/skills/analyze-workout/`) from `tools/workout_context.py`; shown on the workout page, the Week tile and Today.
- `nutrition/`: the Fuel page's data. `intake/<date>.json` = food log (plain-text meals; the `estimate-food` skill fills kcal/macros with `source: "estimate"`), `fuel.json` = quick fuel check per workout (its carbs also go to intervals.icu `carbs_ingested`), `foods.yaml` = during-workout items. Targets are in `app/backend/nutrition.py`; body weight comes from `garmin_data/weight.csv` (Garmin Index scale).
- `app/backend/`: FastAPI. `main.py` = routes; one module per concern, each importing only from the ones above it:
  `store` (paths, file cache, helpers) → `sources` (read synced data, calendar, zones, library, rules) → `body` (load model, cycle, readiness, recovery) and `workouts` (planned workouts, abilities, calendar edits) → `atp` (annual plan) → `week` (Week/Today), `season`, `activity`, `progress`; `nutrition` (Fuel).
- `app/web/`: React + Vite front end, Aurora design. `src/pages/` one file per page, `src/components/` shared parts, `src/styles/` CSS per area.
- `design/`: static design mockups (reference only).

## Run the dashboard
`./start-dashboard.sh`, then open http://localhost:5173. Or start `pulse-api` and `pulse` from `.claude/launch.json`.

## Conventions
- Keep files focused on one goal and roughly 150–500 lines; split a module before it passes ~500.
- Heart-rate and power zones come from intervals.icu (`intervals_data/settings.json`, 7 zones per sport); Garmin zones are only a fallback. Per-workout zone times are intervals.icu's (computed with the zones valid at the time).
- Show training load next to hours, everywhere. Load is intervals.icu's (consistent scale, also on planned workouts) from Mar 2025; fitness/fatigue are intervals.icu CTL/ATL.
- Activities are de-duplicated in `app/backend/sources.py` (watch + Edge record the same ride); never sum raw CSV rows for totals.
- intervals.icu history (and comparable load) starts March 2025; older load shows as "—".
- Week files are edited line-by-line by the dashboard (drag & drop), so keep one session per line: `- { date: …, workout: … }`.
- Past seasons run from 1 Sep to the first Sunday of July.
