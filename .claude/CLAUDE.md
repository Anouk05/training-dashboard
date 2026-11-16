# Training Dashboard: project guide for Claude Code

A local dashboard for endurance training (swim, bike, run, gym). Data comes from Garmin, intervals.icu and
optionally Notion; Claude Code skills plan the season and the week, analyse workouts and estimate food.

## Project layout

| Path | What it is |
|---|---|
| `app/backend/` | FastAPI backend (`main.py` = routes) |
| `app/web/` | React + Vite front end: `src/pages/` one file per page, `src/components/`, `src/styles/` |
| `sync/` | Sync clients: `garmin/`, `intervals.py`, `notion/` |
| `coach/` | `rules.yaml` (hard rules the dashboard checks), `principles.md` (judgment calls), `strength.md` (gym phases and exercises) |
| `library/` | `workouts.yaml` (standard workouts with stable IDs) and `tests.yaml` (test protocols) |
| `nutrition/` | Shared settings: `foods.yaml` (during-workout items), `recipes.example.yaml` |
| `.claude/skills/` | `plan-season`, `plan-week`, `analyze-workout`, `estimate-food` |
| `data/` | Everything personal, never in git (see below) |

## Personal data (`data/`)

| Path | Contents |
|---|---|
| `data/garmin/` | Synced CSVs (activities, daily, training load, HR zones, cycle, weight) and `details/` (per-activity samples). Never edit by hand. |
| `data/intervals/` | Synced activities (load, RPE, notes), wellness (CTL/ATL), `settings.json` (zones) and the full calendar in `events.json` |
| `data/notion/` | `strength.csv`: logged gym sets read back from Notion |
| `data/plans/` | `atp-<season>.yaml` (annual plan), `seasons.yaml` (past seasons), `strength.yaml` (known maxes), `tests.yaml`, `weeks/` (fallback when there's no calendar) |
| `data/reports/` | `workouts/<date>-<activity id>.md` (coach report per workout), `coach/<date>.md` (optional daily note for Today) |
| `data/nutrition/` | `intake/<date>.json` (food log), `fuel.json` (fuel check per workout), `recipes.yaml` |

## Running

- Dashboard: `./start-dashboard.sh`, then open http://localhost:5173 (or start `api` and `web` from `.claude/launch.json`).
- Sync: `.venv/bin/python -m sync` runs everything, like the dashboard's Sync button; `python -m sync garmin|intervals|notion` runs one source, `python -m sync notion plan` pushes planned gym sessions to Notion.

## How things fit together

- **Planning:** the intervals.icu calendar is the source of truth: season start, races (RACE_A/B/C), planned workouts (synced to the watch and bike computer) and weekly notes, which act as phase labels ("Build - week 2"). Write workouts into intervals.icu, not into local files.
- **Coaching:** read `coach/principles.md` and `coach/rules.yaml` before planning or analysing. The planning skills read local-only notes and volume tables first when present (`*.local.md`, `volume-tables.md`, `daily-volume.md`; based on Joe Friel's methods, kept out of git).
- **Workout reports:** the `analyze-workout` skill gathers context with `.claude/skills/analyze-workout/context.py` and writes `data/reports/workouts/…md`; the workout page, the Week tile and Today show it.
- **Strength:** each planned gym session becomes a Notion page with a checklist of exercises and proposed sets × reps @ load (from `app/backend/strength.py` and `coach/strength.md`). Ticked lines, and changes typed after them, come back as logged sets. Needs `NOTION_TOKEN` and `NOTION_PAGE_ID` in `.env`.
- **Fuel:** the `estimate-food` skill fills kcal and macros in the food log (`source: "estimate"`). Targets are in `app/backend/nutrition.py`; body weight comes from the Garmin scale. Fuel-check carbs also go to intervals.icu (`carbs_ingested`).

## Backend modules

Each module imports only from the ones before it:

`store` (paths, file cache, helpers) → `sources` (read synced data, calendar, zones, library, rules) → `body` (load model, cycle, readiness, recovery) and `workouts` (planned workouts, abilities, calendar edits) → `atp` (annual plan) → `week` (Week and Today), `season`, `activity`, `parts`, `progress`, `strength`, `nutrition`.

## Conventions

- Keep files focused on one goal, roughly 150–500 lines; split a module before it passes ~500.
- Heart-rate and power zones come from intervals.icu (7 per sport); Garmin zones are only a fallback. Per-workout zone times are intervals.icu's, computed with the zones valid at the time.
- Show training load next to hours, everywhere. Load is intervals.icu's (same scale on planned workouts); fitness and fatigue are intervals.icu CTL/ATL. Before the intervals.icu history starts there is no comparable load; show "—".
- Activities are de-duplicated in `app/backend/sources.py` (watch and bike computer record the same ride); never sum raw CSV rows for totals.
- The dashboard edits week files line by line (drag and drop), so keep one session per line: `- { date: …, workout: … }`.
- Past seasons run from 1 September to the first Sunday of July.
