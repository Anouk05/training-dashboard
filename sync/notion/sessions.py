"""Gym sessions in Notion: one page per session (for a calendar view) with a checklist of exercises and their
proposed sets × reps @ load. You tick an exercise when you did it as planned, and type what was different at the end
of its line ("45 kg", "3x18", "RPE 7", "knee sore"). Sync reads the ticked lines back as logged sets."""

from __future__ import annotations

import re

from .client import children, config, home_page, plain, query, request, rt, save_config
from .log import setup as setup_log

HOW_TO = ("Tick an exercise when you did it as planned. Did something differently? Type it at the end of the line, "
          "e.g. \"45 kg\", \"3x18\", \"15, 15, 12\", \"RPE 7\" or a note.")


def setup_sessions() -> str:
    """Create the Gym sessions database (once) and link it to the Strength log."""
    cfg = config()
    if cfg.get("sessions_id"):
        return cfg["sessions_id"]
    log = setup_log()
    phases = {"select": {"options": [{"name": c} for c in ("AA", "MT", "MS", "SM")]}}
    db = request("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": home_page()}, "title": rt("Gym sessions"),
        "properties": {"Session": {"title": {}}, "Date": {"date": {}}, "Phase": phases,
                       "Status": {"select": {"options": [{"name": "Planned", "color": "gray"}, {"name": "Done", "color": "green"}]}},
                       "Plan": {"rich_text": {}}}})
    upd = request("PATCH", f"/databases/{log}", {"properties": {
        "Session": {"relation": {"database_id": db["id"], "type": "dual_property", "dual_property": {}}},
        "Planned": {"rich_text": {}}, "Phase": phases}})
    back = upd["properties"]["Session"]["relation"]["dual_property"]["synced_property_name"]
    request("PATCH", f"/databases/{db['id']}", {"properties": {back: {"name": "Exercises"}}})
    save_config(config() | {"sessions_id": db["id"], "sessions_url": db.get("url")})
    return db["id"]


# --------------------------------------------------------------------------- writing the checklist

def _line(ex: dict) -> str:
    return f"{ex['exercise']} · {ex['planned']}" if ex.get("planned") else ex["exercise"]


def _todo(ex: dict) -> dict:
    return {"type": "to_do", "to_do": {"checked": False, "rich_text": rt(ex["exercise"], bold=True) + rt(
        f" · {ex['planned']}" if ex.get("planned") else "")}}


def _body(s: dict) -> list[dict]:
    blocks = [{"type": "callout", "callout": {"rich_text": rt(s["guide"]), "icon": {"type": "emoji", "emoji": "📋"}}}] if s.get("guide") else []
    blocks.append({"type": "paragraph", "paragraph": {"rich_text": rt(HOW_TO)}})
    return blocks + [_todo(e) for e in s["exercises"]]


def _untouched(blocks: list[dict], planned: dict) -> bool:
    """True when nothing on the page was ticked or edited since we wrote it, so it's safe to rewrite."""
    for b in blocks:
        if b["type"] == "to_do":
            if b["to_do"]["checked"] or plain(b["to_do"]) != planned.get(b["id"], {}).get("line"):
                return False
    return True


def push_plan(sessions: list[dict]) -> int:
    """Create or refresh one session page per date with its exercise checklist. A page you already started (ticked or
    typed in) is left alone. sessions: [{date, name, phase, guide, done, exercises: [{exercise, planned, sets, reps, kg}]}]"""
    sdb = setup_sessions()
    cfg = config()
    planned = cfg.get("planned_blocks", {})
    existing = {((p["properties"]["Date"]["date"] or {}).get("start") or "")[:10]: p for p in query(sdb)}
    for s in sessions:
        props = {"Session": {"title": rt(s["name"])}, "Date": {"date": {"start": s["date"]}},
                 "Plan": {"rich_text": rt(" · ".join(_line(e) for e in s["exercises"]))}}
        if s.get("phase"):
            props["Phase"] = {"select": {"name": s["phase"]}}
        page = existing.get(s["date"])
        if page:
            blocks = children(page["id"])
            started = not _untouched(blocks, planned)
            props["Status"] = {"select": {"name": "Done" if s["done"] or started else "Planned"}}
            request("PATCH", f"/pages/{page['id']}", {"properties": props})
            if s["done"] or started:
                continue  # never rewrite a session you've started or logged
            for b in blocks:
                request("DELETE", f"/blocks/{b['id']}")
                planned.pop(b["id"], None)
            new = request("PATCH", f"/blocks/{page['id']}/children", {"children": _body(s)})["results"]
        else:
            props["Status"] = {"select": {"name": "Done" if s["done"] else "Planned"}}
            page = request("POST", "/pages", {"parent": {"database_id": sdb}, "properties": props, "icon": {"type": "emoji", "emoji": "🏋️"}})
            if s["done"]:
                continue  # logged elsewhere (Strength log); no checklist needed
            new = request("PATCH", f"/blocks/{page['id']}/children", {"children": _body(s)})["results"]
        todos = [b for b in new if b["type"] == "to_do"]
        for b, e in zip(todos, s["exercises"]):
            planned[b["id"]] = {"date": s["date"], "exercise": e["exercise"], "line": _line(e),
                                "sets": e.get("sets"), "reps": e.get("reps"), "kg": e.get("kg")}
    save_config(config() | {"planned_blocks": planned})
    print(f"notion: {len(sessions)} gym sessions planned or checked")
    return len(sessions)


# --------------------------------------------------------------------------- reading it back

def _parse(extra: str) -> dict:
    """What you typed after the plan: '45 kg', '3x18', '15, 15, 12', '40s', 'RPE 7', anything else is a note."""
    t, out = extra.strip(" ·-—:,;"), {}
    if m := re.search(r"(\d+)\s*[x×]\s*(\d+)\s*(s|sec)?\b", t, re.I):
        out["sets"], out["reps"] = int(m[1]), m[2] + ("s" if m[3] else "")
        t = t.replace(m[0], " ")
    if m := re.search(r"(\d+(?:[.,]\d+)?)\s*kg\b", t, re.I):
        out["kg"] = float(m[1].replace(",", "."))
        t = t.replace(m[0], " ")
    if m := re.search(r"rpe\s*(\d+(?:[.,]\d)?)", t, re.I):
        out["rpe"] = float(m[1].replace(",", "."))
        t = t.replace(m[0], " ")
    if "reps" not in out and (m := re.search(r"\b(\d+(?:\s*,\s*\d+)+)\b", t)):
        out["reps"] = m[1]
        t = t.replace(m[0], " ")
    note = re.sub(r"\s+", " ", t).strip(" ·-—:,;")
    return out | ({"note": note} if note else {})


def read_checklists() -> list[dict]:
    """Ticked (or annotated) checklist lines as logged sets: the plan, overridden by anything typed after it."""
    cfg = config()
    sdb, planned = cfg.get("sessions_id"), cfg.get("planned_blocks", {})
    rows = []
    for page in query(sdb) if sdb else []:
        day = ((page["properties"]["Date"]["date"] or {}).get("start") or "")[:10]
        for b in children(page["id"]):
            if b["type"] != "to_do" or b["id"] not in planned:
                continue
            p, text = planned[b["id"]], plain(b["to_do"])
            extra = text[len(p["line"]):] if text.startswith(p["line"]) else text.partition(" · ")[2]
            got = _parse(extra) if text != p["line"] else {}
            if not (b["to_do"]["checked"] or got):
                continue
            if not text.startswith(p["line"]):  # you edited the plan itself: read the whole line
                got = _parse(text.partition(" · ")[2])
            rows.append({"date": day, "exercise": p["exercise"], "sets": got.get("sets", p.get("sets")),
                         "reps": str(got.get("reps", p.get("reps") or "")), "kg": got.get("kg", p.get("kg")),
                         "rpe": got.get("rpe"), "note": got.get("note", ""), "page_id": b["id"],
                         "edited": b.get("last_edited_time", ""), "source": "checklist"})
    return rows
