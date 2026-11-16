"""Annual training plan (data/plans/atp-*.yaml): read it, edit weeks from the dashboard, and keep the period notes
in intervals.icu in sync."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .store import as_date, cached, PLANS, read_yaml
from .sources import acts, calendar, ev_date, events, RACE_CATS
from .workouts import planned_from_event

# sync clients in sync/ (store puts the project root on sys.path)
from sync import intervals as intervals_sync


def atp() -> dict:
    """Annual training plan from the latest data/plans/atp-*.yaml: one row per week with period, volume, weights and
    abilities, plus races from the intervals.icu calendar and what was planned/done there each week."""
    files = sorted(PLANS.glob("atp-*.yaml"))
    if not files:
        return {}
    p = cached(files[-1], read_yaml)
    t = date.today()
    starts = [as_date(w["start"]) for w in p["weeks"]]
    first, last = starts[0], starts[-1] + timedelta(days=6)
    races = [{"date": e["start_date_local"][:10], "name": e["name"], "priority": e["category"][-1]}
             for e in events() if e["category"] in RACE_CATS and first <= ev_date(e) <= last]
    seen = {(r["date"], r["priority"]) for r in races}
    races += [{"date": str(r["date"]), "name": r["name"], "priority": r["priority"], "not_in_calendar": True}
              for r in p.get("races", []) if (str(r["date"]), r["priority"]) not in seen]
    workouts = calendar(first, last, ("WORKOUT",))
    weeks = []
    for w, ws in zip(p["weeks"], starts):
        we = ws + timedelta(days=6)
        rs, names = [], set()
        for r in sorted(races, key=lambda r: r["date"]):  # two-day regattas are two events: show once
            if ws <= date.fromisoformat(r["date"]) <= we and r["name"] not in names:
                names.add(r["name"]); rs.append(r)
        wk = [planned_from_event(e) for e in workouts if ws <= ev_date(e) <= we]
        row = {**w, "start": ws.isoformat(), "week": ws.isocalendar()[1], "races": rs,
               "calendar_hours": round(sum(x["minutes"] for x in wk) / 60, 1), "calendar_load": sum(x["load"] for x in wk)}
        if ws <= t:
            wa = [a for a in acts() if ws <= a["start"].date() <= we]
            row["done_hours"] = round(sum(a["minutes"] for a in wa) / 60, 1)
            row["done_load"] = round(sum(a["load"] for a in wa))
        weeks.append(row)
    planned = sum(w.get("volume") or 0 for w in weeks)
    return {k: p.get(k) for k in ("athlete", "season", "annual_volume", "annual_tss", "goals", "objectives")} | {
        "file": f"data/plans/{files[-1].name}", "weeks": weeks, "planned_hours": round(planned, 1),
        "planned_tss": sum(w.get("tss") or 0 for w in weeks),
        "done_hours": round(sum(w.get("done_hours") or 0 for w in weeks), 1),
        "done_load": sum(w.get("done_load") or 0 for w in weeks)}


def sport_split_target(ws: date) -> dict | None:
    """The plan's target swim/bike/run split (% of endurance time) for the week starting ws."""
    files = sorted(PLANS.glob("atp-*.yaml"))
    rows = (cached(files[-1], read_yaml) or {}).get("sport_split", []) if files else []
    rows = [r for r in rows if as_date(r["from"]) <= ws]
    return max(rows, key=lambda r: as_date(r["from"])) if rows else None


ATP_PERIODS = ("Prep", "Base 1", "Base 2", "Base 3", "Build 1", "Build 2", "Peak", "Race", "Transition")


ATP_WEIGHTS = ("", "AA", "MT", "MS", "SM")


ATP_ABILITIES = ("AE", "MF", "SS", "ME", "AC", "SP", "T")


def _atp_line(w: dict) -> str:
    v = w.get("volume")
    note = (w.get("note") or "").replace('"', "'").strip()
    t = w.get("tss")
    return ("  - {start: %s, period: %s, volume: %s, tss: %s, weights: %s, swim: [%s], bike: [%s], run: [%s]%s}" % (
        w["start"], w["period"], "null" if v is None else (int(v) if float(v).is_integer() else v),
        "null" if t is None else int(t), w.get("weights") or '""',
        ", ".join(w.get("swim") or []), ", ".join(w.get("bike") or []), ", ".join(w.get("run") or []),
        f', note: "{note}"' if note else ""))


def set_atp_weeks(starts: list[str], changes: dict) -> dict:
    """Edit one or more weeks of the annual plan. The file keeps one week per line, so only those lines are rewritten."""
    files = sorted(PLANS.glob("atp-*.yaml"))
    if not files:
        raise ValueError("no annual plan")
    if "period" in changes and changes["period"] not in ATP_PERIODS:
        raise ValueError(f"unknown period {changes['period']}")
    if "weights" in changes and (changes["weights"] or "") not in ATP_WEIGHTS:
        raise ValueError(f"unknown weights phase {changes['weights']}")
    if "volume" in changes and changes["volume"] is not None:
        changes["volume"] = round(float(changes["volume"]) * 2) / 2  # half hours, like the volume table
        if not 0 <= changes["volume"] <= 40:
            raise ValueError("volume must be 0–40 h")
    if "tss" in changes and changes["tss"] is not None:
        changes["tss"] = int(round(float(changes["tss"])))
        if not 0 <= changes["tss"] <= 2000:
            raise ValueError("TSS must be 0–2000")
    for k in ("swim", "bike", "run"):
        if k in changes:
            changes[k] = [a for a in ATP_ABILITIES if a in (changes[k] or [])]  # canonical order
    p = read_yaml(files[-1])
    by_start = {str(w["start"]): w for w in p["weeks"]}
    lines = files[-1].read_text().splitlines(keepends=True)
    for s in starts:
        if s not in by_start:
            raise ValueError(f"no week starting {s}")
        w = {**by_start[s], **{k: v for k, v in changes.items() if k in ("period", "volume", "tss", "weights", "swim", "bike", "run", "note")}}
        w["start"] = s
        i = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith(f"- {{start: {s},"))
        lines[i] = _atp_line(w) + "\n"
    files[-1].write_text("".join(lines))
    out = atp()
    try:
        out["notes_updated"] = sync_period_notes()
    except Exception as err:  # the plan file is saved either way; report the calendar problem
        out["notes_error"] = str(err)
    return out


PERIOD_NOTE = re.compile(r"^(Prep|Base \d|Build \d|Peak|Race|Transition) - week \d+$")


PERIOD_COLOR = {"Prep": "#4a4a5c", "Transition": "#2c2c36", "Peak": "#b8862e", "Race": "#d9603f"}


def period_notes() -> dict[str, dict]:
    """The weekly note each plan week should have in intervals.icu: "<period> - week <n>" plus hours, weights and focus."""
    out, n, prev = {}, 0, None
    for w in atp().get("weeks", []):
        n = n + 1 if w["period"] == prev else 1
        prev = w["period"]
        bits = [f"{w['volume']} h" if w.get("volume") is not None else "no set volume"]
        bits += [f"{w['tss']} TSS"] if w.get("tss") is not None else []
        bits += [f"weights {w['weights']}"] if w.get("weights") else []
        bits += [w["note"]] if w.get("note") else []
        out[w["start"]] = {"name": f"{w['period']} - week {n}", "description": " · ".join(bits),
                           "color": PERIOD_COLOR.get(w["period"]) or ("#3a4a6b" if w["period"].startswith("Base") else "#2f7a66")}
    return out


def sync_period_notes() -> int:
    """Bring the intervals.icu weekly notes in line with the annual plan. Only period notes are touched:
    a week with a note of your own (e.g. "Baseline tests") keeps it."""
    have = {e["start_date_local"][:10]: e for e in events() if e["category"] == "NOTE" and e.get("for_week")}
    changed = 0
    for start, want in period_notes().items():
        e = have.get(start)
        if e is None:
            intervals_sync.create_week_note(date.fromisoformat(start), want["name"], want["description"], want["color"])
        elif PERIOD_NOTE.match(e["name"] or "") and any((e.get(k) or "") != want[k] for k in want):
            intervals_sync.update_week_note(e["id"], want["name"], want["description"], want["color"])
        else:
            continue
        changed += 1
    if changed:
        intervals_sync.sync_events()
    return changed
