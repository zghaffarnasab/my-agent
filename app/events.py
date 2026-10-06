"""Store events found in emails as suggestions, without duplicates."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app import ai
from app.db import EventStatus, EventSuggestion, SessionLocal, Task
from app.validation import (  # noqa: F401  (re-exported: other modules and tests use these names)
    WARNING_CODES, clean_event as _clean, clean_tz as _clean_tz, clean_warnings as _clean_warnings,
    title_key, url_key,
)

log = logging.getLogger(__name__)


def store_events(task_id: int, cleaned: list[dict], source: str) -> int:
    """Save validated events (see validation.clean_event). Returns how many NEW suggestions were stored.

    The same event often arrives several times (invite + reminder + a forward). It is skipped when an
    existing suggestion, in any email and in any state, has the same link, or the same title and date.
    A cancellation notice marks a not-yet-added suggestion as cancelled.
    """
    if not cleaned:
        return 0
    stored = 0
    with SessionLocal() as db:
        existing = list(db.scalars(select(EventSuggestion)))
        for c in cleaned:
            c = dict(c)
            cancelled = c.pop("cancelled", False)
            ukey, tkey = url_key(c["url"]), title_key(c["title"])
            match = next((
                e for e in existing
                if (ukey and url_key(e.url) == ukey)
                or (tkey and title_key(e.title) == tkey and e.date == c["date"])
                # your reply confirms the time the sender proposed:
                or (e.task_id == task_id and e.date == c["date"] and e.start_time == c["start_time"])
            ), None)
            if match is not None:
                if cancelled and match.status == EventStatus.SUGGESTED:
                    match.status = EventStatus.CANCELLED
                    log.info("Event %s marked as cancelled", match.id)
                continue
            row = EventSuggestion(
                task_id=task_id, source=source, **c,
                status=EventStatus.CANCELLED if cancelled else EventStatus.SUGGESTED,
            )
            db.add(row)
            existing.append(row)
            stored += 1
        db.commit()
    return stored


def extract_for_task(task: Task, *, source: str, text: str, reference: datetime | None = None) -> int:
    """Events-only extraction (sent replies, and the manual "check again" button). Never raises."""
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
    return store_events(task.id, [c for c in (_clean(i) for i in items) if c], source)
