"""Background worker: polls Gmail, drafts replies with Claude, stores them as tasks.

Run with:  python -m app.worker
"""
import logging
import time
from email.utils import parseaddr

from sqlalchemy import select

from app import ai, config, gmail_client
from app.db import SessionLocal, Task, TaskStatus, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def process_new_emails() -> int:
    service = gmail_client.get_service()
    my_address = gmail_client.get_my_address(service).lower()
    ids = gmail_client.list_candidate_message_ids(service, config.GMAIL_QUERY, config.MAX_EMAILS_PER_RUN)

    with SessionLocal() as db:
        known = set(db.scalars(select(Task.gmail_message_id).where(Task.gmail_message_id.in_(ids))))

    created = 0
    for message_id in ids:
        if message_id in known:
            continue
        email = gmail_client.get_message(service, message_id)
        sender = parseaddr(email.from_addr)[1].lower()

        task = Task(
            gmail_message_id=email.id,
            thread_id=email.thread_id,
            from_addr=email.from_addr,
            reply_to=email.reply_to,
            subject=email.subject,
            message_id_header=email.message_id_header,
            references_header=email.references_header,
            received_at=email.received_at,
            original_body=email.body,
        )

        if sender == my_address or email.is_bulk or not email.body.strip():
            task.status = TaskStatus.SKIPPED
            log.info("Skipped %s (%s)", message_id, sender)
        else:
            try:
                task.thread_context = gmail_client.get_thread_context(service, email.thread_id, email.id)
                task.draft_body = ai.draft_reply(
                    from_addr=email.from_addr,
                    subject=email.subject,
                    body=email.body,
                    thread_context=task.thread_context,
                )
                task.status = TaskStatus.PENDING
                created += 1
                log.info("Drafted reply for %s: %s", message_id, email.subject)
            except Exception as exc:  # keep the task so it can be regenerated from the dashboard
                task.status = TaskStatus.FAILED
                task.error = str(exc)[:2000]
                log.exception("Draft failed for %s", message_id)

        with SessionLocal() as db:
            db.add(task)
            db.commit()

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
