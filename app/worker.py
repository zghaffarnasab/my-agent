"""Background worker: polls Gmail, reads every new email, drafts replies only where one is needed.

Run with:  python -m app.worker

For each new email:
  1. Skip it completely if it is our own mail, empty, a mail-system notice, or from a blocked sender.
  2. One cheap AI call classifies it and extracts events, a summary, deadlines and related events.
  3. Only if a real person waits for an answer, a second AI call drafts a reply (status "pending").
     Everything else becomes "info" and is shown under "Other mail".
Nothing is ever sent or added to the calendar here.
"""
import json
import logging
import re
import time
from datetime import datetime, timezone
from email.utils import parseaddr

from sqlalchemy import select

from app import ai, config, events, gmail_client
from app.db import SessionLocal, Task, TaskStatus, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _skip_reason(email, sender: str, my_address: str) -> str | None:
    if sender == my_address:
        return "own mail"
    if not email.body.strip():
        return "empty"
    if email.is_system:
        return "mail-system notice"
    if config.SKIP_SENDERS:
        try:
            if re.search(config.SKIP_SENDERS, sender, re.I):
                return "blocked sender"
        except re.error:
            log.warning("SKIP_SENDERS is not a valid regular expression; ignoring it")
    return None


def _new_task(email) -> Task:
    return Task(
        gmail_message_id=email.id,
        thread_id=email.thread_id,
        from_addr=email.from_addr,
        reply_to=email.reply_to,
        subject=email.subject,
        message_id_header=email.message_id_header,
        references_header=email.references_header,
        received_at=email.received_at,
        original_body=email.body,
        is_bulk=email.is_bulk,
    )


def _save(task: Task) -> None:
    with SessionLocal() as db:
        db.add(task)
        db.commit()


def _read_and_store(service, task: Task, email) -> bool:
    """Classify one email, draft a reply if needed, save everything. Returns True if a draft was made."""
    try:
        result = ai.classify_email(
            text=email.body,
            subject=email.subject,
            from_addr=email.from_addr,
            reference=email.received_at or datetime.now(timezone.utc),
            is_bulk=email.is_bulk,
        )
    except Exception as exc:
        log.exception("Classification failed for %s", email.id)
        task.error = str(exc)[:2000]
        # Bulk mail is not worth a visible error; a person's email stays visible so it can be retried by hand
        task.status = TaskStatus.SKIPPED if email.is_bulk else TaskStatus.FAILED
        _save(task)
        return False

    task.category = result["category"]
    task.needs_reply = result["needs_reply"]
    task.summary = result["summary"]
    task.is_forward = result["is_forward"]
    task.original_from = result["original_from"]
    task.original_subject = result["original_subject"]
    task.original_date = result["original_date"]
    task.related_json = json.dumps(result["related_events"], ensure_ascii=False) if result["related_events"] else ""
    task.action_items_json = json.dumps(result["action_items"], ensure_ascii=False) if result["action_items"] else ""

    drafted = False
    if result["needs_reply"]:
        try:
            task.thread_context = gmail_client.get_thread_context(service, email.thread_id, email.id)
            task.draft_body = ai.draft_reply(
                from_addr=email.from_addr,
                subject=email.subject,
                body=email.body,
                thread_context=task.thread_context,
            )
            task.status = TaskStatus.PENDING
            drafted = True
            log.info("Drafted reply for %s: %s", email.id, email.subject)
        except Exception as exc:  # keep the task so it can be regenerated from the dashboard
            task.status = TaskStatus.FAILED
            task.error = str(exc)[:2000]
            log.exception("Draft failed for %s", email.id)
    else:
        task.status = TaskStatus.INFO   # never "pending": it needs no reply
        log.info("Read %s as %s (no reply needed): %s", email.id, task.category, email.subject)

    _save(task)
    n = events.store_events(task.id, result["events"], source="incoming")
    if n:
        log.info("Found %d new event(s) in %s", n, email.id)
    return drafted


def process_new_emails() -> int:
    service = gmail_client.get_service()
    my_address = gmail_client.get_my_address(service).lower()
    # Ask for more than we will process: already-known emails stay unread and would otherwise fill the list
    list_limit = min(500, max(50, config.MAX_EMAILS_PER_RUN * 3))
    ids = gmail_client.list_candidate_message_ids(service, config.GMAIL_QUERY, list_limit)

    with SessionLocal() as db:
        known = set(db.scalars(select(Task.gmail_message_id).where(Task.gmail_message_id.in_(ids))))

    created = read = bulk_read = 0
    for message_id in ids:
        if message_id in known:
            continue
        if read >= config.MAX_EMAILS_PER_RUN:
            log.info("Per-run limit reached (%d); the rest waits for the next run.", config.MAX_EMAILS_PER_RUN)
            break
        email = gmail_client.get_message(service, message_id)
        sender = parseaddr(email.from_addr)[1].lower()
        task = _new_task(email)

        reason = _skip_reason(email, sender, my_address)
        if reason or (email.is_bulk and not config.PROCESS_BULK):
            task.status = TaskStatus.SKIPPED
            _save(task)
            log.info("Skipped %s (%s): %s", message_id, reason or "bulk mail, PROCESS_BULK is off", sender)
            continue

        if email.is_bulk:
            if bulk_read >= config.MAX_BULK_PER_RUN:
                log.info("Bulk limit reached (%d); %s waits for the next run.", config.MAX_BULK_PER_RUN, message_id)
                continue
            bulk_read += 1

        read += 1
        if _read_and_store(service, task, email):
            created += 1

    return created


def main() -> None:
    init_db()
    log.info("Worker started. Polling every %s seconds.", config.POLL_INTERVAL_SECONDS)
    while True:
        try:
            if gmail_client.connected_email() is None:
                log.info("Gmail not connected yet. Waiting...")
            else:
                n = process_new_emails()
                if n:
                    log.info("Created %d new draft(s).", n)
        except Exception:
            log.exception("Polling cycle failed")
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
