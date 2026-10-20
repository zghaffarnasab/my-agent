"""Store events found in emails as suggestions, without duplicates."""
import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import ai, i18n, settings
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


def deadline_events(result: dict, reference: datetime) -> list[dict]:
    """Dated action items -> all-day "Deadline: ..." suggestions (same shape as validation.clean_event).

    Newsletters and promotions are left out (their "register by" dates are noise), and so is bulk mail
    unless it was flagged urgent (official reminders often come from automated senders).
    """
    if result.get("category") == "newsletter_promo":
        return []
    if result.get("is_bulk") and not result.get("urgent"):
        return []
    tz = settings.get_timezone()
    today = reference.astimezone(ZoneInfo(tz)).date().isoformat()
    prefix = i18n.translate(settings.get_language(), "ev.deadline_prefix")
    out = []
    for item in result.get("action_items") or []:
        if not item.get("due") or item["due"] < today:
            continue
        out.append({
            "title": f"{prefix} {item['text']}"[:200],
            "date": item["due"], "end_date": "", "start_time": "", "end_time": "", "timezone": tz,
            "location": "", "url": "", "description": result.get("urgent_reason", ""),
            "warnings": "", "cancelled": False,
        })
    return out


def store_classified(task_id: int, result: dict, reference: datetime) -> int:
    """Events of one classified email plus its deadlines. Returns how many NEW suggestions were stored."""
    return store_events(task_id, list(result["events"]) + deadline_events(result, reference), source="incoming")


def reread_task(task: Task) -> int:
    """The "check this email again" button: read the email again like the worker does (urgency, deadlines,
    events). The task's status and reply draft are not changed. Falls back to events only if the call fails."""
    reference = task.received_at or datetime.now(timezone.utc)
    try:
        result = ai.classify_email(text=task.original_body, subject=task.subject, from_addr=task.from_addr,
                                   reference=reference, is_bulk=task.is_bulk)
    except Exception:
        log.exception("Reading task %s again failed; looking for events only", task.id)
        return extract_for_task(task, source="incoming", text=task.original_body, reference=reference)
    result["is_bulk"] = task.is_bulk
    with SessionLocal() as db:
        row = db.get(Task, task.id)
        if row is not None:
            row.is_urgent, row.urgent_reason = result["urgent"], result["urgent_reason"]
            if result["action_items"]:
                row.action_items_json = json.dumps(result["action_items"], ensure_ascii=False)
            db.commit()
    return store_classified(task.id, result, reference)
