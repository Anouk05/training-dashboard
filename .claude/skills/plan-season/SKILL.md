---
name: plan-season
description: Build or change the annual training plan (ATP) for a season with Joe Friel's periodisation method — goals, training objectives, annual volume, race priorities, periods, weekly hours and TSS, weights and abilities per week. Use when the user wants to plan a season or a new A race, change periods or blocks, or asks how many hours to train in a period.
---

# Plan the season (annual training plan)

Method to build an annual training plan, based on Joe Friel's methods. **If `method.local.md` and `volume-tables.md` exist in this folder** (your own notes and tables, kept out of git), read them first: they take precedence over the summary and the fallback rule below.

## In this project
- Read first: `coach/principles.md` (and `coach/principles.local.md` if present), `coach/rules.yaml`, the athlete
  context in memory, past seasons (`/api/seasons`) and the current plan (`plans/atp-*.yaml`).
- Go through the steps with the athlete one question round at a time, with a recommended option. Don't fill in
  goals, objectives or race priorities yourself.
- Use the weekly volumes exactly as the tables (or the fallback rule) give them; raise concerns in the chat instead
  of easing weeks on your own judgement.
- Save the plan in `plans/atp-<season>.yaml`, one week per line (format at the top of that file). The dashboard edits
  the same lines; `app/backend/atp.py` keeps the weekly notes ("Base 1 - week 2 · 10 h · 480 TSS") in sync with
  intervals.icu. Writing them to intervals.icu the first time needs the athlete's OK.
- Races come from the intervals.icu calendar (RACE_A/B/C). Propose adding missing races; add them only after a yes.
- Before raising volume, check energy availability and recovery (Fuel and Recovery pages).

## Steps
1. **Season goals.** One to three, measurable, about outcomes the athlete controls (a time beats a placing).
2. **Training objectives.** Up to four checkpoints that show a limiter is improving, each with a number and a date
   (e.g. "running effiency factor +10 % by March").
3. **Annual volume.** Compare three estimates and agree on annual training hours: last season's total (+~10 % if it went well),
   a typical week × 45–50, and what the longest goal race usually asks for.
4. **Race priorities.** A races (at most three, spread out, each with a peak and taper), B races (a few rest days
   before), C races (treated as workouts).
5. **Periods.** Work backwards from the first A race: race week, peak (1–2 weeks), build 1–2, base 1–3, prep before
   that, transition after. Blocks of about four weeks with the last week lighter (three-week blocks suit older or
   slower-recovering athletes). General fitness before race-specific work.
6. **Weekly volume.** From the tables, or with the fallback rule below.
7. **Weights and abilities per week.** Weights phases: AA in prep, MT if time allows, MS in base 1(–2), then SM
   (see `coach/strength.md`). Abilities: aerobic endurance and speed skills throughout base, force and muscular
   endurance from base 2, aerobic capacity in build where the race calls for it; test weeks at the end of base blocks.

## Fallback rule for weekly hours (without the tables)
Average week = annual hours ÷ 50. Multiply by the period factor:

| Period | Week 1 | Week 2 | Week 3 | Week 4 |
|---|---|---|---|---|
| Prep | 0.8 | 0.8 | 0.8 | 0.8 |
| Base 1–3 | 1.0 | 1.15 | 1.3 | 0.65 |
| Build 1–2 | 1.2 | 1.2 | 1.2 | 0.65 |
| Peak | 1.0 | 0.8 | | |
| Race | 0.65 | | | |
| Transition | free | | | |

Round to the half hour. TSS works the same way from annual TSS.

The user can also fill in their own preferred weekly hours per training phase (e.g. base 10 h, build 12 h, recovery weeks 6 h), then use those instead.

The plan is a guide, it is not completely fixed: shorten or lengthen periods when the athlete responds faster or slower, as long
as general work comes before specific work.
