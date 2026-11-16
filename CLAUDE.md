# Sport: training data, plans and the Training Dashboard

## Layout
- `garmin_sync.py`: incremental Garmin Personal API sync, writes to `garmin_data/` (`python3 garmin_sync.py`). The code is in `garmin/`: `client.py` (auth, HTTP, CSV helpers), `activities.py`, `wellness.py` (daily, zones, training load, cycle, weight).
- `intervals_sync.py`: incremental intervals.icu sync, writes to `intervals_data/` (activities with load/RPE/notes, wellness with CTL/ATL, the full calendar in `events.json`). It also has `move_event()` for rescheduling planned workouts. The dashboard's Sync button runs both scripts.
- `notion_sync.py`: strength training in Notion (code in `notion/`). Each planned gym session is a page in "Gym sessions" (calendar) with a checklist of exercises and proposed sets × reps @ load from `app/backend/strength.py`; ticked lines (and changes typed after them) are read back as logged sets into `notion_data/strength.csv`. Older sessions logged in the "Strength log" database are read too. Sync runs it; `python3 notion_sync.py plan` pushes the plan. Needs NOTION_TOKEN and NOTION_PAGE_ID in `.env`; your known maxes are in `plans/strength.yaml`.
- `garmin_data/`: generated CSVs (`activities`, `daily`, `training_load`, `hr_zones`, `cycle` = menstrual cycles from Garmin cycle tracking, `weight`) plus `details/` (per-activity samples cache). Never edit by hand.
- **The intervals.icu calendar is the source of truth for the plan**: season start, races (RACE_A/B/C), planned workouts (synced to the watch and Edge) and notes (weekly notes act as phase labels, e.g. "Build - week 2"). To plan, write workouts into intervals.icu, not into local files.
- `plans/seasons.yaml`: past seasons (windows, goals, extra results). `plans/weeks/` is only a fallback when there's no calendar.
- `library/workouts.yaml`: standard workouts with stable IDs (`RUN-THR-2k`, …); `match` regexes link Garmin activities to them.
- `coach/rules.yaml`: hard rules checked by the dashboard. `coach/principles.md`: judgment calls (fuller local notes in `coach/principles.local.md`, not in git); read them before planning or analysing. `coach/strength.md`: strength principles, exercises and the weight-lifting phase table (AA/MT/MS/SM) the dashboard uses for gym targets.
- Skills in `.claude/skills/`: `plan-season` (annual plan), `plan-week` (weekly routine); each has a short public SKILL.md, and local-only `method.local.md` plus the volume tables (`volume-tables.md`, `daily-volume.md`) based on Joe Friel's methods, kept out of git, `analyze-workout`, `estimate-food`.
- `reports/coach/<date>.md`: optional daily coach note; when present, the Today page shows it instead of the auto-check.
- `reports/workouts/<date>-<activity id>.md`: coach report per completed workout, written by the `analyze-workout` skill (`.claude/skills/analyze-workout/`) from `tools/workout_context.py`; shown on the workout page, the Week tile and Today.
- `nutrition/`: the Fuel page's data. `intake/<date>.json` = food log (plain-text meals; the `estimate-food` skill fills kcal/macros with `source: "estimate"`), `fuel.json` = quick fuel check per workout (its carbs also go to intervals.icu `carbs_ingested`), `foods.yaml` = during-workout items, `recipes.yaml` = your recipes (local only; `recipes.example.yaml` shows the format). Targets are in `app/backend/nutrition.py`; body weight comes from `garmin_data/weight.csv` (Garmin Index scale).
- `app/backend/`: FastAPI. `main.py` = routes; one module per concern, each importing only from the ones above it:
  `store` (paths, file cache, helpers) → `sources` (read synced data, calendar, zones, library, rules) → `body` (load model, cycle, readiness, recovery) and `workouts` (planned workouts, abilities, calendar edits) → `atp` (annual plan) → `week` (Week/Today), `season`, `activity`, `progress`; `nutrition` (Fuel).
- `app/web/`: React + Vite front end, Aurora design. `src/pages/` one file per page, `src/components/` shared parts, `src/styles/` CSS per area.

## Run the dashboard
`./start-dashboard.sh`, then open http://localhost:5173. Or start `api` and `web` from `.claude/launch.json`.

## Conventions
- Keep files focused on one goal and roughly 150–500 lines; split a module before it passes ~500.
- Heart-rate and power zones come from intervals.icu (`intervals_data/settings.json`, 7 zones per sport); Garmin zones are only a fallback. Per-workout zone times are intervals.icu's (computed with the zones valid at the time).
- Show training load next to hours, everywhere. Load is intervals.icu's (consistent scale, also on planned workouts); fitness/fatigue are intervals.icu CTL/ATL.
- Activities are de-duplicated in `app/backend/sources.py` (watch + Edge record the same ride); never sum raw CSV rows for totals.
- Before your intervals.icu history starts there is no comparable load; it shows as "—".
- Week files are edited line-by-line by the dashboard (drag & drop), so keep one session per line: `- { date: …, workout: … }`.
- Past seasons run from 1 Sep to the first Sunday of July.
