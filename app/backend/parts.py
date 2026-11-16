"""A completed workout split along its planned steps (warm-up, drills, main set, …), from intervals.icu's 1-second
streams: power, NP, heart rate, cadence, pace and efficiency factor per part. Cached per activity and plan text."""

from __future__ import annotations

import hashlib
import json
import re

from .store import ICU
from .workouts import _step_kind, _step_minutes

import intervals_sync  # project root (store puts it on sys.path)

CACHE = ICU / "parts"


def blocks(desc: str | None) -> list[dict]:
    """intervals.icu workout text -> [{reps, steps: [(minutes, text)]}], keeping 'Nx' repeat blocks together."""
    out, cur, mult = [], [], 1
    def close():
        if cur:
            out.append({"reps": mult, "steps": list(cur)})
    for line in (desc or "").splitlines() + [""]:
        s = line.strip()
        rep = re.match(r"^(\d+)\s*x\b", s, re.I)
        if rep or not s:
            close()
            cur, mult = [], int(rep[1]) if rep else 1
            continue
        if s.startswith("-"):
            body = s[1:].strip()
            mins = _step_minutes(body, _step_kind(body))
            if mins:
                cur.append((mins, body))
    # one-step blocks one after another stay separate parts; a repeat block is one part per step position
    split = []
    for b in out:
        if b["reps"] == 1 and len(b["steps"]) > 1:
            split += [{"reps": 1, "steps": [s]} for s in b["steps"]]
        else:
            split.append(b)
    return split


def _label(b: dict, pos: int, i: int, bl: list[dict]) -> str:
    text = b["steps"][pos][1].lower()
    if b["reps"] > 1:
        if pos > 0 or (len(b["steps"]) > 1 and b["steps"][0][0] > b["steps"][1][0] * 1.5):
            return "Between reps"
        return "Cadence reps" if "rpm" in text else "Reps"
    longest = max(range(len(bl)), key=lambda k: bl[k]["steps"][0][0] * bl[k]["reps"] * len(bl[k]["steps"]))
    if i == longest:
        return "Main set"
    if i == 0:
        return "Warm-up"
    if i == len(bl) - 1:
        return "Cool-down"
    return f"Block {i + 1}"


def _np(w: list) -> float | None:
    if len(w) < 30:
        return None
    roll = [sum(w[k - 30:k]) / 30 for k in range(30, len(w) + 1)]
    return (sum(x ** 4 for x in roll) / len(roll)) ** .25


def _stats(idx: list[int], s: dict, sport: str) -> dict:
    hr = [s["heartrate"][k] for k in idx if s["heartrate"][k]]
    w = [s["watts"][k] or 0 for k in idx] if s.get("watts") else []
    cad = [s["cadence"][k] for k in idx if s.get("cadence") and (s["cadence"][k] or 0) > 20]
    v = [s["velocity_smooth"][k] for k in idx if s.get("velocity_smooth") and (s["velocity_smooth"][k] or 0) > .5]
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    hr_a, w_a, v_a = avg(hr), avg(w) if any(w) else None, avg(v)
    np_ = _np(w) if any(w) else None
    cad_a = avg(cad)
    if cad_a and sport == "run" and cad_a < 120:  # intervals.icu gives run cadence per leg
        cad_a *= 2
    out = {"avg_hr": round(hr_a) if hr_a else None, "avg_watts": round(w_a) if w_a else None, "np": round(np_) if np_ else None,
           "cadence": round(cad_a) if cad_a else None,
           "pace": round(1000 / v_a / 60, 2) if v_a and sport == "run" else None}
    # efficiency factor: NP (or avg power) per heartbeat on the bike, metres per minute per heartbeat on foot
    if hr_a and sport == "run" and v_a:
        out["ef"] = round(v_a * 60 / hr_a, 2)
    elif hr_a and (np_ or w_a):
        out["ef"] = round((np_ or w_a) / hr_a, 2)
    return out


def _decoupling(idx: list[int], s: dict, sport: str) -> float | None:
    """Pw:HR (or pace:HR) drift between the first and second half of a part, in %."""
    if len(idx) < 1200:
        return None
    def ef(half):
        hr = [s["heartrate"][k] for k in half if s["heartrate"][k]]
        if not hr:
            return None
        if sport == "run":
            v = [s["velocity_smooth"][k] or 0 for k in half] if s.get("velocity_smooth") else []
        else:
            v = [s["watts"][k] or 0 for k in half] if s.get("watts") else []
        return (sum(v) / len(v)) / (sum(hr) / len(hr)) if v and any(v) else None
    skip = idx[300:] if len(idx) > 1800 else idx  # first 5 minutes: heart rate still settling into the new block
    a, b = ef(skip[:len(skip) // 2]), ef(skip[len(skip) // 2:])
    return round((a - b) / a * 100, 1) if a and b else None


def parts(icu_id: str, desc: str | None, sport: str) -> list[dict]:
    """One row per part of the plan. Parts follow the planned durations from the start; the last part runs to the end."""
    bl = blocks(desc)
    if len(bl) < 2 or not icu_id:
        return []
    key = hashlib.sha1((desc or "").encode()).hexdigest()[:10]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{icu_id}-{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    raw = intervals_sync.get(f"/activity/{icu_id}/streams?types=time,heartrate,watts,cadence,velocity_smooth") or []
    s = {x["type"]: x.get("data") or [] for x in raw}
    t = s.get("time") or []
    if not t or not s.get("heartrate"):
        return []
    # planned timeline: (start s, end s, part key)
    timeline, at = [], 0.0
    for i, b in enumerate(bl):
        for r in range(b["reps"]):
            for pos, (mins, _) in enumerate(b["steps"]):
                timeline.append((at, at + mins * 60, (i, pos), r))
                at += mins * 60
    timeline[-1] = (timeline[-1][0], float("inf"), timeline[-1][2], timeline[-1][3])
    groups: dict = {}
    reps: dict = {}
    j = 0
    for k, ti in enumerate(t):
        while j < len(timeline) - 1 and ti >= timeline[j][1]:
            j += 1
        _, _, pk, r = timeline[j]
        groups.setdefault(pk, []).append(k)
        reps.setdefault(pk, {}).setdefault(r, []).append(k)
    out = []
    for i, b in enumerate(bl):
        for pos, (mins, text) in enumerate(b["steps"]):
            idx = groups.get((i, pos), [])
            if not idx:
                continue
            row = {"label": _label(b, pos, i, bl), "target": text, "reps": b["reps"],
                   "start": t[idx[0]], "end": t[idx[-1]] + 1, "minutes": round(len(idx) / 60, 1)} | _stats(idx, s, sport)
            if b["reps"] > 1:  # cadence and power per rep: are the drills consistent?
                ix = [reps[(i, pos)][r] for r in sorted(reps[(i, pos)])]
                row["per_rep"] = [{k: p[k] for k in ("avg_watts", "cadence", "avg_hr", "pace")} | {"start": t[x[0]], "end": t[x[-1]] + 1}
                                  for p, x in ((_stats(x, s, sport), x) for x in ix)]
                row.pop("ef", None)  # heart rate lags too much on short reps for EF to mean anything
            elif row["minutes"] < 5:
                row.pop("ef", None)
            row["decoupling"] = _decoupling(idx, s, sport)
            out.append(row)
    f.write_text(json.dumps(out))
    return out
