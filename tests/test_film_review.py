"""Review pages for the filmmaker dashboard (/film), reading the pipeline's Postgres.

The not-configured test always runs. The data tests need PIPELINE_TEST_DATABASE_URL (an empty throwaway
database, wiped by the test), like tests/test_pipeline_db.py.
"""
import os

import pytest

from app import config, i18n

URL = os.getenv("PIPELINE_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="PIPELINE_TEST_DATABASE_URL not set")


def test_film_keys_exist_in_both_languages():
    known = set(i18n.messages("en"))
    from app import filmdash
    for s in filmdash.STATUSES:
        assert f"film_status.{s}" in known and f"flash.film_{s}" in known
    for s in filmdash.DATE_STATUSES:
        assert f"film_date.{s}" in known
    for u in filmdash.UK_ELIGIBLE:
        assert f"film_uk.{u}" in known
    for k in filmdash.TABLES:
        assert f"film_kind.{k}" in known
    for _, key in filmdash.FUND_FIELDS + filmdash.EVENT_FIELDS:
        assert key in known


def test_not_configured(client, monkeypatch):
    monkeypatch.setattr(config, "FILMDASH_DATABASE_URL", "")
    page = client.get("/film")
    assert page.status_code == 200 and "FILMDASH_DATABASE_URL" in page.text
    assert 'href="/film"' not in client.get("/").text      # no menu link when not connected


def test_needs_login():
    from fastapi.testclient import TestClient
    from app import main
    r = TestClient(main.app).get("/film", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.fixture()
def film_db(monkeypatch):
    from test_pipeline_db import FakeClaude, PAGE, SEED, _http, _tool_output
    from pipeline import db, runner, sources
    with db.connect(URL) as c:
        c.autocommit = True
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.autocommit = False
        db.migrate(c)
        sources.seed(c, SEED)
        runner.run(c, claude_client=FakeClaude(_tool_output()), http_client=_http([PAGE]))
        fund_id = c.execute("SELECT id FROM funds").fetchone()["id"]
    monkeypatch.setattr(config, "FILMDASH_DATABASE_URL", URL)
    return fund_id


@needs_db
def test_list_detail_and_approve(client, film_db):
    assert 'href="/film"' in client.get("/").text
    page = client.get("/film")
    assert "Documentary Development Fund" in page.text and "2026-11-09" in page.text

    detail = client.get(f"/film/fund/{film_db}")
    assert detail.status_code == 200
    assert "closes on 21 December 2026 at 13:00" in detail.text          # the quote is shown
    assert "25,000–40,000 GBP" in detail.text
    assert "Lab starts" not in detail.text                                # the invented date was dropped

    r = client.post(f"/film/fund/{film_db}/review", data={"status": "published", "note": "checked"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Documentary Development Fund" not in client.get("/film").text
    assert "Documentary Development Fund" in client.get("/film?status=published").text

    from pipeline import db
    with db.connect(URL) as c:
        row = c.execute("SELECT status::text AS s, review_note, reviewed_at FROM funds").fetchone()
    assert row["s"] == "published" and row["review_note"] == "checked" and row["reviewed_at"]


@needs_db
def test_bad_input(client, film_db):
    assert client.get("/film/article/1").status_code == 404
    assert client.get("/film/fund/999999").status_code == 404
    assert client.post(f"/film/fund/{film_db}/review", data={"status": "deleted"}).status_code == 400


@needs_db
def test_persian_page(client, film_db):
    client.cookies.set("lang", "fa")
    page = client.get(f"/film/fund/{film_db}")
    assert 'dir="rtl"' in page.text and "تاریخ‌ها" in page.text
