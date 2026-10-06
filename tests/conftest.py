import os
import sys
import tempfile

# Fake settings, set BEFORE the app is imported. No real keys, no real Gmail/Google/Anthropic calls.
_tmp = tempfile.mkdtemp()
os.environ.update({
    "SECRET_KEY": "test-secret",
    "DASHBOARD_PASSWORD": "test-password",
    "GOOGLE_CLIENT_ID": "x",
    "GOOGLE_CLIENT_SECRET": "x",
    "ANTHROPIC_API_KEY": "x",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "BASE_URL": "http://localhost:8000",
    "DEFAULT_LANGUAGE": "en",
    "TIMEZONE": "Europe/London",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    from app.db import init_db
    init_db()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app import settings
    settings._cache.clear()
    yield
    settings._cache.clear()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Every test starts with no tasks and no events."""
    from app.db import EventSuggestion, SessionLocal, Task
    with SessionLocal() as db:
        db.query(EventSuggestion).delete()
        db.query(Task).delete()
        db.commit()


@pytest.fixture()
def client(monkeypatch):
    """A logged-in browser with fake Gmail/Calendar data (no real API calls)."""
    from datetime import datetime, timedelta, timezone

    from fastapi.testclient import TestClient

    from app import calendar_client, gmail_client, main

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
