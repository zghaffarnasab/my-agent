"""End-to-end pipeline test against a throwaway Postgres: migrate, seed, fetch, extract (fake Claude), store.

Skipped unless PIPELINE_TEST_DATABASE_URL points at an EMPTY test database; the test wipes its
public schema. Example: PIPELINE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5544/filmdash_test
"""
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from pipeline import db, fetch, runner, sources

URL = os.getenv("PIPELINE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="PIPELINE_TEST_DATABASE_URL not set")

PAGE_URL = "https://funds.example.org/documentary-development"
PAGE = (Path(__file__).parent / "fixtures" / "pipeline_fund_page.html").read_text()
SEED = {
    "organisations": [{"name": "Example Film Body", "website": "https://funds.example.org"}],
    "sources": [{"url": PAGE_URL, "organisation": "Example Film Body", "title": "Dev fund",
                 "tier": "official", "method": "html", "feeds_kind": "fund"}],
}


def _tool_output(closes="2026-12-21", closes_quote="closes on 21 December 2026 at 13:00"):
    return {
        "notes": "One fund, round 2.",
        "items": [{
            "kind": "fund", "slug": "example-documentary-development-fund", "name": "Documentary Development Fund",
            "organisation": "Example Film Body", "strand": "Round 2",
            "summary": "Development grants for UK-based documentary filmmakers.",
            "stages": ["development"], "forms": ["documentary", "feature"], "genres": [],
            "amount_min": 25000, "amount_max": 40000, "amount_currency": "GBP", "amount_status": "confirmed",
            "deadline_mode": "rounds", "is_accepting": True, "residency_rule": "Lead director resident in the UK",
            "uk_eligible": "yes",
            "dates": [
                {"kind": "opens", "label": "Round 2", "status": "confirmed", "date_value": "2026-11-09",
                 "time_value": "13:00", "tz": "Europe/London",
                 "source_quote": "Round 2 opens on 9 November 2026 at 13:00"},
                {"kind": "deadline", "label": "Round 2", "status": "confirmed", "date_value": closes,
                 "time_value": "13:00", "tz": "Europe/London", "source_quote": closes_quote},
                {"kind": "results", "label": "Round 2", "status": "expected", "approx_text": "Spring 2027",
                 "approx_from": "2027-03-01", "approx_to": "2027-05-31",
                 "source_quote": "Decisions will be announced in Spring 2027."},
                # invented: not on the page, must be rejected
                {"kind": "event_start", "status": "confirmed", "date_value": "2027-06-01",
                 "source_quote": "Lab starts 1 June 2027"},
            ],
            "evidence": [
                {"field": "amount", "value": "25000-40000",
                 "source_quote": "grants of between £25,000 and £40,000"},
                {"field": "uk_eligible", "value": "yes", "source_quote": "The lead director must be resident in the UK."},
                {"field": "residency_rule", "value": "UK resident director",
                 "source_quote": "The lead director must be resident in the UK."},
            ],
            "confidence": 0.9,
        }],
    }


class FakeClaude:
    def __init__(self, output):
        self.output = output
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        block = SimpleNamespace(type="tool_use", name="record_extraction", input=self.output)
        return SimpleNamespace(content=[block], stop_reason="tool_use",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


def _http(page):
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=page[0])))


@pytest.fixture()
def conn():
    with db.connect(URL) as c:
        c.autocommit = True
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.autocommit = False
        assert db.migrate(c) == ["001_schema.sql"]
        assert db.migrate(c) == []          # second run does nothing
        sources.seed(c, SEED)
        yield c


def test_full_run_stores_drafts_with_quotes(conn):
    page = [PAGE]
    claude = FakeClaude(_tool_output())
    result = runner.run(conn, claude_client=claude, http_client=_http(page))
    assert result["fetched"] == 1 and result["changed"] == 1 and result["errors"] == []

    # The prompt saw the cleaned page, not the menu or footer.
    message = claude.calls[0]["messages"][0]["content"]
    assert "Round 2 opens on 9 November 2026" in message and "Cookie settings" not in message
    assert claude.calls[0]["tool_choice"]["type"] == "auto"
    assert "calling the record_extraction tool" in message

    fund = conn.execute("SELECT *, stages::text[] AS stages FROM funds").fetchone()
    assert fund["status"] == "draft" and fund["uk_eligible"] == "yes"
    assert (fund["amount_min"], fund["amount_max"], fund["amount_status"]) == (25000, 40000, "confirmed")
    assert fund["stages"] == ["development"]

    dates = conn.execute("SELECT kind, status, date_value, approx_text FROM current_dates ORDER BY kind").fetchall()
    assert [(d["kind"], d["status"]) for d in dates] == [("opens", "confirmed"), ("deadline", "confirmed"),
                                                          ("results", "expected")]
    run = conn.execute("SELECT * FROM extraction_runs").fetchone()
    assert run["ok"] and run["input_tokens"] == 1000
    assert [r["what"] for r in run["rejected_items"]] == ["date:event_start:"]
    assert conn.execute("SELECT count(*) AS n FROM field_evidence").fetchone()["n"] == 3
    assert conn.execute("SELECT count(*) AS n FROM review_queue").fetchone()["n"] == 1

    # Same page again: no new snapshot, no new Claude call.
    result = runner.run(conn, force=True, claude_client=claude, http_client=_http(page))
    assert result["changed"] == 0 and len(claude.calls) == 1


def test_changed_deadline_supersedes_old_row(conn):
    page = [PAGE]
    runner.run(conn, claude_client=FakeClaude(_tool_output()), http_client=_http(page))

    page[0] = PAGE.replace("closes on 21 December 2026", "closes on 8 January 2027")
    claude = FakeClaude(_tool_output("2027-01-08", "closes on 8 January 2027 at 13:00"))
    result = runner.run(conn, force=True, claude_client=claude, http_client=_http(page))
    assert result["changed"] == 1
    assert conn.execute("SELECT count(*) AS n FROM funds").fetchone()["n"] == 1   # same record updated

    rows = conn.execute("SELECT date_value, superseded_at FROM record_dates WHERE kind = 'deadline' ORDER BY id")\
        .fetchall()
    assert str(rows[0]["date_value"]) == "2026-12-21" and rows[0]["superseded_at"] is not None
    assert str(rows[1]["date_value"]) == "2027-01-08" and rows[1]["superseded_at"] is None
    assert conn.execute("SELECT count(*) AS n FROM date_conflicts").fetchone()["n"] == 0


def test_fetch_error_is_recorded(conn):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    [res] = fetch.fetch_due(conn, client=client)
    assert res.error == "HTTP 503" and not res.changed
    src = conn.execute("SELECT * FROM sources").fetchone()
    assert src["last_error"] == "HTTP 503" and src["last_http_status"] == 503
    assert runner.pending_snapshots(conn) == []
