"""Website visits (/stats): read-only statistics from the website's `site_visits` table.

The data tests need PIPELINE_TEST_DATABASE_URL (an empty throwaway database, wiped by the test), like
tests/test_site_requests.py. The table is created here the way the website's migration does.
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from app import config, i18n, settings, sitestats

URL = os.getenv("PIPELINE_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="PIPELINE_TEST_DATABASE_URL not set")

VISITS_TABLE = """
CREATE TABLE IF NOT EXISTS site_visits (
  id bigserial PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), path text NOT NULL,
  referrer text, lang text, device text, visitor text NOT NULL)
"""


def test_keys_exist():
    for lang in i18n.SUPPORTED:
        known = set(i18n.messages(lang))
        for key in sitestats.DEVICES:
            assert f"stats_device.{key}" in known
        for key in sitestats.LANGS:
            assert f"stats_lang.{key}" in known
        for label in sitestats.KNOWN_PATHS.values():
            assert f"stats_path.{label}" in known


def test_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "FILMDASH_DATABASE_URL", "")
    page = client.get("/stats")
    assert page.status_code == 200 and "FILMDASH_DATABASE_URL" in page.text
    assert 'href="/stats"' not in client.get("/").text      # no menu link when not connected


def test_needs_login():
    from fastapi.testclient import TestClient
    from app import main
    r = TestClient(main.app).get("/stats", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.fixture()
def visits_db(monkeypatch):
    from pipeline import db
    with db.connect(URL) as c:
        c.autocommit = True
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.autocommit = False
        c.execute(VISITS_TABLE)
        c.commit()
    monkeypatch.setattr(config, "FILMDASH_DATABASE_URL", URL)
    monkeypatch.setattr(settings, "get_timezone", lambda: "Europe/London")
    return db


def _add(db, rows):
    with db.connect(URL) as c:
        for when, path, ref, lang, device, visitor in rows:
            c.execute("INSERT INTO site_visits (created_at, path, referrer, lang, device, visitor) "
                      "VALUES (%s, %s, %s, %s, %s, %s)", (when, path, ref, lang, device, visitor))
        c.commit()


@needs_db
def test_summary_counts(visits_db):
    today = date(2026, 10, 19)
    at = lambda d, h: datetime(d.year, d.month, d.day, h, tzinfo=timezone.utc)
    yesterday = today - timedelta(days=1)
    _add(visits_db, [
        (at(today, 10), "/", "google.com", "en", "desktop", "a"),
        (at(today, 10), "/opportunities", None, "en", "desktop", "a"),
        (at(today, 11), "/", None, "fa", "mobile", "b"),
        (at(yesterday, 9), "/", "instagram.com", "fa", "mobile", "a"),   # same hash, other day: a new visitor-day
        (at(today - timedelta(days=40), 9), "/", None, "en", "desktop", "old"),
        # 23:30 UTC on 18 Oct is 00:30 on 19 Oct in London (summer time): counted as today
        (datetime(2026, 10, 18, 23, 30, tzinfo=timezone.utc), "/confirm", None, "en", "tablet", "c"),
    ])
    s = sitestats.summary(7, today=today)
    assert s["views"] == 5 and s["visitors"] == 4
    assert s["today"] == {"day": today, "views": 4, "visitors": 3, "pct": 100}
    assert len(s["daily"]) == 7 and s["daily"][-2]["views"] == 1
    assert [(p["path"], p["views"], p["visitors"], p["label"]) for p in s["pages"]] == [
        ("/", 3, 3, "home"), ("/confirm", 1, 1, "confirm"), ("/opportunities", 1, 1, "opportunities")]
    assert [(r["referrer"], r["views"]) for r in s["referrers"]] == [("google.com", 1), ("instagram.com", 1)]
    assert {d["key"]: d["n"] for d in s["devices"]} == {"mobile": 2, "tablet": 1, "desktop": 1}
    assert sitestats.summary(90, today=today)["views"] == 6
    assert sitestats.summary(12345, today=today)["days"] == 30          # unknown period falls back to 30


@needs_db
def test_page(client, visits_db):
    page = client.get("/stats?days=7")
    assert page.status_code == 200 and "No visits counted" in page.text
    _add(visits_db, [(datetime.now(timezone.utc), "/", "google.com", "en", "mobile", "a")])
    page = client.get("/stats?days=7")
    assert "google.com" in page.text and 'href="/stats?days=90"' in page.text
    assert 'href="/stats"' in client.get("/").text


@needs_db
def test_missing_table(client, visits_db):
    with visits_db.connect(URL) as c:
        c.execute("DROP TABLE site_visits")
        c.commit()
    assert "has not created its visits table" in client.get("/stats").text
