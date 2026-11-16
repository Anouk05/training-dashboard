"""The Strength log database: one row per exercise per session (Exercise, Date, Sets, Reps, Load (kg), RPE, Note).
Older sessions were logged here; new ones are ticked off on the session checklists (notion/sessions.py)."""

from __future__ import annotations

from datetime import date

from .client import config, home_page, plain, query, request, rt, save_config

# Your gym routine: the exercises on each planned session. Change it here, or just edit a session's checklist.
ROUTINE = ["Double leg squat", "Leg press", "Single leg squat", "Power step-up", "Leg curl", "Core"]
LOAD_NAMES = ("kg", "load(kg)", "load", "weight", "weight(kg)")


def setup() -> str:
    """Create the Strength log database on the shared page (once) and remember its id."""
    cfg = config()
    if cfg.get("database_id"):
        return cfg["database_id"]
    db = request("POST", "/databases", {
        "parent": {"type": "page_id", "page_id": home_page()},
        "title": rt("Strength log"),
        "properties": {"Exercise": {"title": {}}, "Date": {"date": {}}, "Sets": {"number": {"format": "number"}},
                       "Reps": {"rich_text": {}}, "Load (kg)": {"number": {"format": "number"}},
                       "RPE": {"number": {"format": "number"}}, "Note": {"rich_text": {}}}})
    save_config(cfg | {"database_id": db["id"], "url": db.get("url")})
    print(f"Created Strength log: {db.get('url')}")
    return db["id"]


def add_rows(day: date | None = None, exercises: list[str] | None = None) -> int:
    """Add one empty row per exercise for a session (the old way of logging; checklists are easier)."""
    db = setup()
    day = day or date.today()
    for ex in exercises or ROUTINE:
        request("POST", "/pages", {"parent": {"database_id": db}, "properties": {
            "Exercise": {"title": rt(ex)}, "Date": {"date": {"start": day.isoformat()}}}})
    return len(exercises or ROUTINE)


def read_log() -> list[dict]:
    """Rows of the Strength log that have numbers in them."""
    db = config().get("database_id")
    if not db:
        return []
    rows = []
    for p in query(db):
        pr = p["properties"]
        kg = next((v for k, v in pr.items() if k.lower().replace(" ", "") in LOAD_NAMES), {})
        row = {"date": ((pr.get("Date", {}).get("date") or {}).get("start") or "")[:10], "exercise": plain(pr.get("Exercise", {})).strip(),
               "sets": pr.get("Sets", {}).get("number"), "reps": plain(pr.get("Reps", {})).strip(), "kg": kg.get("number"),
               "rpe": pr.get("RPE", {}).get("number"), "note": plain(pr.get("Note", {})).strip(), "page_id": p["id"],
               "edited": p.get("last_edited_time", ""), "source": "log"}
        if row["date"] and row["exercise"] and (row["reps"] or row["sets"] or row["kg"] is not None):
            rows.append(row)
    return rows


def archive_empty(after: str) -> int:
    """Move empty planned rows (no numbers) dated after a day to the trash; the session checklists replace them."""
    db = config().get("database_id")
    n = 0
    for p in query(db, {"filter": {"property": "Date", "date": {"after": after}}}) if db else []:
        pr = p["properties"]
        kg = next((v for k, v in pr.items() if k.lower().replace(" ", "") in LOAD_NAMES), {})
        if not (plain(pr.get("Reps", {})) or pr.get("Sets", {}).get("number") or kg.get("number") is not None):
            request("PATCH", f"/pages/{p['id']}", {"archived": True})
            n += 1
    return n
