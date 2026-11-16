---
name: plan-week
description: Plan a training week or a standard weekly routine from the annual plan — anchor and breakthrough workouts, two-a-days, sport distribution, daily volume, peak and race-week routines, missed workouts — and put the workouts into intervals.icu. Use when the user asks for a plan for this or next week, wants to rearrange a week, or asks what to do after missed sessions.
---

# Plan the week (weekly routine)

Method for planning a training week, based on Joe Friel's methods. **If `method.local.md` and `daily-volume.md` exist in this folder** (your own notes and tables, kept out of git),
read them first: they take precedence over the summary and the fallback rule below.

## In this project
- Inputs: the week in `plans/atp-*.yaml` (period, hours, TSS, weights, abilities, focus) and its `sport_split` target,
  `coach/principles.md` (and `coach/principles.local.md` if present), `coach/rules.yaml`, readiness and recent load
  (`/api/today`, `/api/week`), and the athlete's anchors and preferences (ask).
- Keep the week's total from the annual plan; distribute it over the days with the daily tables or the fallback rule.
- Write workouts in intervals.icu workout text (`- 10m 120w`, `- 45m Z1-Z2 HR`, `6x` repeats; power in W from the
  current FTP). Add an `Abilities: AE, SS` line when the abilities aren't obvious from the steps.
- Show the plan in the chat first. Create the workouts with `intervals_sync.create_event` only after the athlete
  says yes, then run `python3 intervals_sync.py`.
- Check the Week page's coach rules (e.g. load ramp) and report a rule break instead of quietly changing the volume.
- Mention fuelling for long or hard sessions (the Fuel page's targets).
- Gym sessions: take sets, reps and load from `coach/strength.md` for the week's weights phase and the next-session
  targets on Progress → Strength (`/api/strength`); once the gym session is in intervals.icu, Sync (or
  `python3 notion_sync.py plan`) puts its checklist with proposed loads in Notion.

## How to build the week
1. **Keep weeks alike.** A stable routine is easier to follow and to compare.
2. **Ask for preferences and fixed points** first: pool times, group rides, busy days. Place these anchors, then
   build around them.
3. **Hard days.** About 80 % of the time easy (Z1–2), the rest hard (Z4–5): typically two hard days a week, with an
   easy day after each. Fewer hard sessions rather than more when in doubt. Gym sessions in prep and early base count
   as hard and need two days between them; later in the season one moderate gym session a week.
4. **Sport spread.** At least three sessions per sport when possible, spaced over the week; extra sessions go to the
   weakest sport (or the bike).
5. **Two-a-days.** Fine for experienced athletes, but don't stack them day after day. Run first when legs should be
   fresh; do the limiting sport first.
6. **Long sessions.** Put the long run midweek or on a different day from the long ride, so both are done fresh.
7. **Fill the rest** with recovery and skills sessions until the week's total is reached.
8. **Bricks** (short run off the bike) fit the build period.
9. **Peak and race week.** Less volume each week, short race-pace efforts every few days, one very easy day two days
   before the race, a short pre-race session the day before.
10. **Missed sessions.** Up to three days: carry on, don't make up. Longer: treat it as recovery, and after illness
    step back a block before moving on.

## Fallback rule for daily volume (without the tables)
Of the weekly hours: two longest days ≈ 20–25 % each, one rest or very short day (≤ 10 %), the rest spread evenly
over the other days, no day above 30 %. Round to quarter hours and keep the weekly total.

The athlete can also give their own preferred hours per day (e.g. Tuesday 1 h, Saturday 3 h); use those instead.
