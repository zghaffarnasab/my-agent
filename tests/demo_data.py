"""Fake data and fake services for trying the dashboard locally. Nothing here talks to a real database,
Gmail, Google Calendar or Anthropic, and every name, address and link is made up."""
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "demo"


def configure_env(port: int = 8765) -> str:
    """Set fake settings BEFORE the app is imported. A temporary database is created, never a real one."""
    folder = tempfile.mkdtemp(prefix="gmail-ai-demo-")
    os.environ.update({
        "SECRET_KEY": "demo-secret", "DASHBOARD_PASSWORD": PASSWORD,
        "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x", "ANTHROPIC_API_KEY": "x",
        "DATABASE_URL": f"sqlite:///{folder}/demo.db", "BASE_URL": f"http://127.0.0.1:{port}",
        "TIMEZONE": "Europe/London",
    })
    os.environ.pop("DEFAULT_LANGUAGE", None)    # the built-in default (English) is what we want to see
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    return folder


def _day(offset: int) -> str:
    return (datetime.now(ZoneInfo("Europe/London")).date() + timedelta(days=offset)).isoformat()


def seed() -> dict:
    from app.db import EventSuggestion, SessionLocal, Task, TaskStatus, init_db
    init_db()
    now = datetime.now(timezone.utc)
    ids = {}

    def task(key, status, subject, sender, body, minutes_ago, **kw):
        with SessionLocal() as db:
            t = Task(gmail_message_id=f"demo-{key}", thread_id=f"th-{key}", from_addr=sender, reply_to=sender,
                     subject=subject, received_at=now - timedelta(minutes=minutes_ago), original_body=body,
                     status=status, **kw)
            db.add(t)
            db.commit()
            ids[key] = t.id

    def event(key, task_key, title, date, **kw):
        with SessionLocal() as db:
            e = EventSuggestion(task_id=ids[task_key], title=title, date=date, timezone=kw.pop("timezone", "Europe/London"), **kw)
            db.add(e)
            db.commit()
            ids[key] = e.id

    task("film", TaskStatus.PENDING, "Film Night on Thursday?", "Alex Example <alex@example.com>",
         "Hi!\n\nWe are showing a short film on Thursday 19:30 at Studio 4. Would you like to come? "
         "Please let me know by Wednesday.\n\nAlex", 25,
         draft_body="Hi Alex,\n\nThanks for the invitation. I would love to join the film night on Thursday.\n\nBest regards",
         category="needs_reply", needs_reply=True, summary="Alex invites you to a film night on Thursday at 19:30.")
    event("film_ev", "film", "Film Night", _day(3), start_time="19:30", end_time="21:00", location="Studio 4, London",
          url="https://events.example.com/film-night", warnings="year_missing", description="Short film screening.")
    event("film_ev2", "film", "Team call", _day(3), start_time="19:00", end_time="20:00", timezone="America/New_York",
          warnings="timezone_guessed")

    long_body = "Hello,\n\nPlease find our quote for the teaser project below.\n\n" + \
        "\n".join(f"Item {i}: editing, colour grading and sound mix, estimated {i * 2} hours." for i in range(1, 25)) + \
        "\n\nBest wishes,\nAnna"
    task("quote", TaskStatus.PENDING, "Quote for the teaser project", "Anna Weber <anna@example.com>", long_body, 95,
         draft_body="Hi Anna,\n\nThanks for the quote. I will review it and get back to you by the end of the week.\n\nBest regards",
         category="needs_reply", needs_reply=True, summary="Anna sends a price quote for the teaser project.")
    task("fa", TaskStatus.PENDING, "جلسه‌ی هماهنگی نمایش", "Sara Example <sara@example.com>",
         "سلام، پنج‌شنبه ساعت ۱۰ صبح برای جلسه مناسب است؟ لطفاً خبر بده.\nسارا", 180,
         draft_body="سلام سارا،\n\nپنج‌شنبه ساعت ۱۰ مناسب است. می‌بینمت.\n\nبا احترام",
         category="needs_reply", needs_reply=True, summary="Sara asks if Thursday 10:00 works for a meeting.")
    event("fa_ev", "fa", "جلسه‌ی هماهنگی", _day(5), start_time="10:00", location="Office")
    task("contract", TaskStatus.FAILED, "Contract question", "Jon Example <jon@example.com>",
         "Could you confirm clause 4 before Friday?", 400, error="Anthropic API is not reachable (demo).")

    task("fwd", TaskStatus.INFO, "Fwd: You are invited to Example Capital: Winter Summit Pre Meet",
         "Alex Forwarder <forwarder@example.com>",
         "---------- Forwarded message ---------\nFrom: Sam Host <host@events.example.com>\n\nDrinks 5-8pm on 17th November.",
         240, category="event_invite", summary="Forwarded invitation to a pre-summit drinks evening in London.",
         is_forward=True, original_from="Sam Host <host@events.example.com>",
         original_subject="You are invited to Example Capital: Winter Summit Pre Meet", original_date="Sun, Oct 4, 2026",
         related_json='[{"title": "Other Summit Meetup", "url": "https://events.example.com/other1"}, {"title": "Side Event"}]',
         action_items_json='[{"text": "Register before the deadline", "due": "%s"}]' % _day(10))
    event("fwd_ev", "fwd", "Example Capital: Winter Summit Pre Meet", _day(12), end_date=_day(14), start_time="17:00",
          end_time="20:00", location="London, United Kingdom", url="https://events.example.com/abc123",
          warnings="conflicting_times,location_hidden", description="Drinks 5-8 pm, then a private dinner at 8 pm.")
    task("news", TaskStatus.INFO, "Weekly film news", "Film News <news@example.com>", "This week: a webinar on colour grading.",
         600, category="newsletter_promo", summary="Newsletter with a webinar about colour grading.", is_bulk=True)
    event("news_ev", "news", "Colour grading webinar", _day(8), start_time="14:00", end_time="15:00", url="https://events.example.com/webinar")
    event("news_ev2", "news", "Cancelled screening", _day(9), status="cancelled", url="https://events.example.com/off")
    task("receipt", TaskStatus.INFO, "Your receipt from Example Shop", "Example Shop <no-reply@example.com>", "Thank you for your order.",
         900, category="receipt_notification", summary="Receipt for an order of 2 items.", is_bulk=True)
    task("old", TaskStatus.DONE, "Archived notice", "Notice <notice@example.com>", "Old notice.", 3000,
         category="info_fyi", summary="An old notice that was archived.")

    task("sent1", TaskStatus.SENT, "Re: Location scouting", "Mia Example <mia@example.com>", "Can you send the address?", 1500,
         draft_body="Hi Mia,\n\nThe address is 12 Example Street.\n\nBest", sent_at=now - timedelta(days=1))
    task("sent2", TaskStatus.SENT, "Re: Invoice", "Accounts <accounts@example.com>", "Please confirm the invoice.", 2000,
         draft_body="Confirmed, thank you.", sent_at=now - timedelta(days=2))
    task("rej", TaskStatus.REJECTED, "Quick question", "Lee Example <lee@example.com>", "Do you have a minute?", 2500,
         draft_body="Sure, what is it about?")
    return ids


def install_fakes(sent_log: list | None = None) -> None:
    """Replace everything that would reach the outside world."""
    from types import SimpleNamespace

    from app import ai, calendar_client, events, gmail_client
    import app.worker as worker

    sent_log = sent_log if sent_log is not None else []
    soon = datetime.now(timezone.utc) + timedelta(days=1)

    gmail_client.connected_email = lambda: "owner@example.com"
    gmail_client.has_calendar_access = lambda: True
    gmail_client.get_service = lambda: object()
    gmail_client.get_thread_context = lambda s, t, e, max_messages=5: "From: Someone\n\nAn earlier message in this thread."
    gmail_client.mark_as_read = lambda *a, **k: None

    def send_reply(service, **kw):
        time.sleep(0.3)
        sent_log.append(kw)
        return "sent-id"
    gmail_client.send_reply = send_reply

    calendar_client.upcoming = lambda *a, **k: [
        calendar_client.UpcomingEvent("Dentist", soon, soon + timedelta(hours=1), soon.date(), False, "", "https://example.com/e"),
        calendar_client.UpcomingEvent("Holiday", None, None, (soon + timedelta(days=2)).date(), True, "", "")]
    calendar_client.conflicts = lambda s: [
        calendar_client.UpcomingEvent("Dentist", soon, None, soon.date(), False, "", "")] if s.title == "Film Night" else []
    calendar_client.find_duplicate = lambda s: None
    calendar_client.create_event = lambda s, invite=None: {"id": "demo-event", "htmlLink": "https://calendar.example/demo"}

    def draft_reply(**kw):
        time.sleep(0.4)
        note = f" [rewritten: {kw['instruction']}]" if kw.get("instruction") else ""
        return "Hi,\n\nThank you for your message. I will get back to you soon." + note + "\n\nBest regards"
    ai.draft_reply = draft_reply
    events.extract_for_task = lambda *a, **k: 0
    worker.process_new_emails = lambda: 0
