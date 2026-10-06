"""Render every page in both languages with fake Gmail/Calendar data (no real API calls)."""
import re
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import calendar_client, gmail_client, main
from app.db import EventSuggestion, SessionLocal, Task, TaskStatus

ISOLATES = re.compile("[⁦-⁩]")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(gmail_client, "connected_email", lambda: "owner@example.com")
    monkeypatch.setattr(gmail_client, "has_calendar_access", lambda: True)
    soon = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(calendar_client, "upcoming", lambda *a, **k: [
        calendar_client.UpcomingEvent("Dentist", soon, soon + timedelta(hours=1), soon.date(), False, "", "https://example.com/e"),
        calendar_client.UpcomingEvent("", None, None, soon.date(), True, "", ""),
    ])
    monkeypatch.setattr(calendar_client, "conflicts", lambda s: [
        calendar_client.UpcomingEvent("Dentist", soon, None, soon.date(), False, "", "")])
    c = TestClient(main.app)
    assert c.post("/login", data={"password": "test-password"}, follow_redirects=False).status_code == 303
    return c


@pytest.fixture()
def task_id():
    with SessionLocal() as db:
        task = Task(gmail_message_id=f"m-{datetime.now().timestamp()}", thread_id="t1",
                    from_addr="Alex Example <alex@example.com>", reply_to="alex@example.com",
                    subject="Can we meet?", received_at=datetime.now(timezone.utc),
                    original_body="Hi, lunch on 17.11 at 10:30?", draft_body="Sure!", status=TaskStatus.PENDING)
        db.add(task)
        db.commit()
        db.add_all([
            EventSuggestion(task_id=task.id, title="Lunch", date="2026-11-17", start_time="10:30", end_time="11:30",
                            timezone="America/New_York", location="London", warnings="year_missing,location_hidden"),
            EventSuggestion(task_id=task.id, title="Old style", date="2026-11-18", start_time="09:00",
                            timezone="Europe/London", ambiguity="legacy free text"),
            EventSuggestion(task_id=task.id, title="Done one", date="2026-11-19", start_time="09:00", end_time="10:00",
                            timezone="Europe/London", status="added", html_link="https://example.com/x"),
        ])
        db.commit()
        return task.id


def _plain(html: str) -> str:
    return ISOLATES.sub("", html)


@pytest.mark.parametrize("lang,direction", [("en", "ltr"), ("fa", "rtl")])
def test_every_page_renders_in_both_languages(client, task_id, lang, direction):
    client.cookies.set("lang", lang)
    for path in ("/", "/?status=sent", "/changelog", "/settings", f"/tasks/{task_id}"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert f'<html lang="{lang}" dir="{direction}">' in r.text, path
        assert "{{" not in r.text and "{%" not in r.text
    client.cookies.clear()
    client.cookies.set("lang", lang)
    login = client.get("/login")
    assert login.status_code == 200 and f'dir="{direction}"' in login.text


def test_english_pages_have_no_persian_text(client, task_id):
    client.cookies.set("lang", "en")
    for path in ("/", "/changelog", "/settings", f"/tasks/{task_id}"):
        text = client.get(path).text.replace("فارسی", "")
        assert not re.search(r"[؀-ۿ]", text), path


def test_persian_task_page_translates_warning_codes_and_keeps_times_ltr(client, task_id):
    client.cookies.set("lang", "fa")
    html = _plain(client.get(f"/tasks/{task_id}").text)
    assert "سال در ایمیل نیامده بود" in html            # year_missing
    assert "مکان دقیق نمایش داده نشده" in html           # location_hidden
    assert "legacy free text" in html                    # old rows keep their stored text
    assert '<input type="time" dir="ltr"' in html        # times are forced left-to-right
    assert "(10:30)" not in html and "10:30" in html


def test_english_task_page_shows_translated_warnings(client, task_id):
    client.cookies.set("lang", "en")
    html = _plain(client.get(f"/tasks/{task_id}").text)
    assert "The email did not give a year" in html
    assert "America/New_York, not your local time" in html


def test_dashboard_marks_today_and_untitled(client):
    client.cookies.set("lang", "en")
    html = _plain(client.get("/").text)
    assert "(untitled)" in html and "Dentist" in html and "Tomorrow," in html


def test_language_switch_sets_cookie_and_blocks_open_redirect(client):
    r = client.post("/language", data={"lang": "fa", "next": "/changelog"}, follow_redirects=False)
    assert r.headers["location"] == "/changelog" and "lang=fa" in r.headers["set-cookie"]
    r = client.post("/language", data={"lang": "en", "next": "//evil.example.com"}, follow_redirects=False)
    assert r.headers["location"] == "/"
    r = client.post("/language", data={"lang": "de", "next": "/"}, follow_redirects=False)
    assert "lang=" not in r.headers.get("set-cookie", "")


def test_settings_save_language_and_timezone(client):
    r = client.post("/settings", data={"language": "fa", "tz": "Europe/London"}, follow_redirects=False)
    assert r.status_code == 303
    from app import settings
    settings._cache.clear()
    assert settings.get_language() == "fa" and settings.get_timezone() == "Europe/London"
    bad = client.post("/settings", data={"language": "en", "tz": "Mars/Base"}, follow_redirects=False)
    assert bad.status_code == 303
    settings._cache.clear()
    assert settings.get_language() == "fa"            # the bad save changed nothing
    client.post("/settings", data={"language": "en", "tz": ""}, follow_redirects=False)
    settings._cache.clear()
    assert settings.get_language() == "en" and settings.get_timezone() == "Europe/London"   # falls back to env
    client.cookies.clear()


def test_flash_message_follows_the_language_of_the_next_page(client, monkeypatch):
    import app.worker
    monkeypatch.setattr(app.worker, "process_new_emails", lambda: 0)   # never touch Gmail
    client.cookies.set("lang", "en")
    client.post("/poll-now", follow_redirects=False)
    client.cookies.set("lang", "fa")
    assert "بررسی صندوق شروع شد" in client.get("/").text
