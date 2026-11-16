---
name: analyze-workout
description: Analyse completed workouts (after sync) against the plan, zones, earlier sessions, recovery and the coach rules, and write a short coach report that the dashboard shows on the workout page. Use when the user asks to analyse a workout ("analyse today's run", "how did my test go"), or with no argument to analyse every recent workout that has no report yet (this is what the scheduled run does).
---

# Analyse workout

Arguments: an activity id, `latest`, or nothing (= every completed workout of the last 7 days without a report).
Work from the project root (the folder with CLAUDE.md).

## 1. Get fresh data
```bash
python3 garmin_sync.py && python3 intervals_sync.py
```
If a sync fails (network, rate limit), continue with the data that's there and say so in your reply.

## 2. Pick the workouts
- An id or `latest`: just that one.
- No argument: `.venv/bin/python tools/workout_context.py --pending` lists workouts without a report.
  Nothing pending → reply "No new workouts to analyse." and stop.
- More than 5 pending: analyse the 5 most recent, list the rest as skipped.

## 3. Gather context (per workout)
```bash
.venv/bin/python tools/workout_context.py <id>
```
Read once per run as well: `coach/principles.md` (and `coach/principles.local.md` if present), `coach/rules.yaml`, and the athlete context in memory
(current season and goals, injuries or health notes to keep in mind).
Don't open the raw CSVs; the JSON has what you need.

## 4. Analyse
Judge the session against what it was meant to be. Look at, in this order:
1. **Plan vs done**: duration, intended zones/targets (`planned.description`) vs what happened; `compliance`.
2. **Intensity**: minutes per zone (`hr_zone_minutes_current_zones`, or `power_zone_minutes` for power-only rides).
   An easy session with time in Z3+ is a finding; a test or interval session is judged on its reps and targets.
3. **Execution**: rep consistency (`reps`: pace/HR spread), pacing of tests (even vs fading), drift
   (`halves.decoupling_pct`: < 5 % good aerobic control, > 8 % worth mentioning, unless it's a hard session).
3b. **Per part of the plan** (`parts`, from 1-second data; also shown as a table on the workout page): judge each
   part against its own target. Drills: cadence per rep (`per_rep`) vs the rpm in `target`, and how far cadence drops
   between reps. Main set: power in its target range, EF (NP per heartbeat; metres/min per heartbeat on runs) and
   `decoupling` (< 5 % good). Warm-up EF is usually lower; compare main set with main set. Name the part in the bullet
   (e.g. "Main set: EF 0.98, drift 1 %"): per-part numbers aren't in the header, so they may be quoted.
4. **Response vs earlier**: `m_per_beat` (speed per heartbeat) or power at HR against `earlier_comparable`.
   Only call it progress/regress when the difference is clear (> ~3 %) and conditions are comparable.
5. **Subjective**: RPE, feel and notes (notes may be Dutch). Mismatch between RPE and HR is worth a line.
6. **Context**: readiness that day (incl. `readiness_that_day.cycle`: menstrual cycle day and phase), ACWR (`load_context.acwr`), week rules, calendar notes (injury, recovery weeks). A higher resting HR, lower HRV or higher RPE in the luteal phase is expected; mention the phase when it explains a number, not as a problem.
7. **Tests** (`6m test`, `30m test`, LTHR test): compute the result. For a 30-minute test: FTP ≈ average power of the
   30-minute effort (use reps/halves or the planned 30′ block), LTHR ≈ average HR of its last 20 minutes. Compare with
   the current settings (FTP in `workout.ftp`, LTHR in `zones_used.lthr`) and say whether to update them.

Be concrete and honest. Use the numbers. Don't praise by default; say what was good, what to change, and why.
Never invent data that isn't in the JSON. If heart rate or power is missing, say what that limits.

## 5. Write the report
Write it to `report_path` from the JSON (e.g. `reports/workouts/2026-11-04-12345678901.md`), in English.
The workout page already shows distance, time, pace/power, heart rate, load, RPE, the heart-rate chart and time in
zones right above the report, so **don't repeat those numbers**. Only use a number when it carries the point
(drift, a comparison with earlier sessions, a test result). Short, scannable, no filler:

```markdown
---
activity_id: "12345678901"
date: 2026-11-04
title: Easy and controlled, efficiency back at its usual level   # the verdict, ≤ 60 characters
rating: on_target        # on_target | easier | harder | missed | test | unplanned
flags: []                # short tags for problems, e.g. [hr_drift, too_hard_for_easy, no_heart_rate, rpe_high]
---
- ✓ Fully in Z1–Z2 with flat heart rate after the warm-up (2.6 % drift).
- ✓ 1.16 m per heartbeat, in line with your last few weeks.
- → Friday: same flat loop, same heart rate, so the baseline compares directly.
- → Add a line in your notes on how your legs felt.
```
Rules for the body: 2–4 bullets, each one line (max ~15 words). `✓` = went well, `→` = to do / change next time,
`!` = a concern (use sparingly). For a test, start with `- **Result:** FTP ≈ … W · LTHR ≈ … bpm` and add
`result: {ftp: …, lthr: …}` to the frontmatter. A suggestion for the next planned session (see `next_planned`) goes in
a `→` bullet; don't edit the calendar yourself.

## 6. Reply
List each analysed workout with its title, plus anything that needs the user's attention (a suggested change to an
upcoming session, a zone/FTP update after a test). The dashboard shows the reports on each workout's page.
