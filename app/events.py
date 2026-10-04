"""Find events in an email and store them as suggestions next to the task."""
import logging
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import ai, config
from app.db import EventSuggestion, SessionLocal, Task

log = logging.getLogger(__name__)
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _clean_time(value) -> str:
    m = TIME_RE.match(str(value or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def _clean_tz(value) -> str:
    try:
        return ZoneInfo(str(value)).key
    except Exception:
        return config.TIMEZONE


def _clean(item: dict) -> dict | None:
    try:
        d = date.fromisoformat(str(item.get("date", "")).strip())
    except ValueError:
        return None
    return {
        "title": str(item.get("title") or "")[:500],
        "date": d.isoformat(),
        "start_time": _clean_time(item.get("start_time")),
        "end_time": _clean_time(item.get("end_time")),
        "timezone": _clean_tz(item.get("timezone")),
        "location": str(item.get("location") or "")[:500],
        "description": str(item.get("description") or "")[:2000],
        "ambiguity": str(item.get("ambiguity") or "")[:1000],
    }


def extract_for_task(task: Task, *, source: str, text: str, reference: datetime | None = None) -> int:
    """Run extraction and store suggestions. Never raises; returns how many were stored."""
    try:
        items = ai.extract_events(
            text=text,
            subject=task.subject,
            from_addr=task.from_addr,
            reference=reference or task.received_at or datetime.now(timezone.utc),
            outgoing=(source == "outgoing"),
        )
    except Exception:
        log.exception("Event extraction failed for task %s", task.id)
        return 0

    cleaned = [c for c in (_clean(i) for i in items) if c]
    if not cleaned:
        return 0
    stored = 0
    with SessionLocal() as db:
        existing = {
            (e.date, e.start_time)
            for e in db.scalars(select(EventSuggestion).where(EventSuggestion.task_id == task.id))
        }
        for c in cleaned:
            key = (c["date"], c["start_time"])
            if key in existing:   # e.g. your reply confirms the time the sender proposed
                continue
            existing.add(key)
            db.add(EventSuggestion(task_id=task.id, source=source, **c))
            stored += 1
        db.commit()
    return stored
