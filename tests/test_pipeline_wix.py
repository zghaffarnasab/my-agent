"""Wix sync of published funds/events, against a fake Wix API (no real calls).

The payload tests always run. The sync tests need PIPELINE_TEST_DATABASE_URL (an empty throwaway database,
wiped by the test), like tests/test_pipeline_db.py.
"""
import json
import os
from datetime import date, time

import httpx
import pytest

from pipeline import wix

URL = os.getenv("PIPELINE_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="PIPELINE_TEST_DATABASE_URL not set")


def test_item_id_is_stable_and_per_kind():
    assert wix.item_id("fund", 7) == wix.item_id("fund", 7)
    assert wix.item_id("fund", 7) != wix.item_id("event", 7)


def test_money_and_dates_text():
    assert wix._money(25000, 40000, "GBP") == "GBP 25,000 - 40,000"
    assert wix._money(None, 1000000, "GBP") == "GBP 1,000,000"
    assert wix._money(None, None, None) is None
    text = wix._dates_text([
        {"kind": "deadline", "label": "Round 2", "status": "confirmed", "date_value": date(2026, 12, 21),
         "time_value": time(13, 0), "approx_text": None},
        {"kind": "results", "label": None, "status": "expected", "date_value": None, "time_value": None,
         "approx_text": "Spring 2027"},
    ])
    assert text == "21 Dec 2026 13:00: Round 2 (deadline)\nSpring 2027: results [expected]"


class FakeWix:
    """Minimal in-memory Wix Data API: collections, bulk save, bulk remove."""

    def __init__(self):
        self.collections, self.items, self.calls = {}, {}, []

    def handler(self, req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "test-key" and req.headers["wix-site-id"] == "site-1"
        body = json.loads(req.content) if req.content else {}
        path = req.url.path.removeprefix("/wix-data/v2")
        self.calls.append((req.method, path))
        if req.method == "GET" and path.startswith("/collections/"):
            cid = path.rsplit("/", 1)[1]
            if cid not in self.collections:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json={"collection": self.collections[cid]})
        if path == "/collections":
            self.collections[body["collection"]["id"]] = body["collection"]
            self.items[body["collection"]["id"]] = {}
            return httpx.Response(200, json=body)
        if path == "/collections/create-field":
            self.collections[body["dataCollectionId"]]["fields"].append(body["field"])
            return httpx.Response(200, json={})
        if path == "/bulk/items/save":
            store = self.items[body["dataCollectionId"]]
            for d in body["dataItems"]:
                store[d["id"]] = d["data"]
            return httpx.Response(200, json={"results": [
                {"itemMetadata": {"id": d["id"], "originalIndex": i, "success": True}}
                for i, d in enumerate(body["dataItems"])]})
        if path == "/bulk/items/remove":
            store = self.items[body["dataCollectionId"]]
            for i in body["dataItemIds"]:
                store.pop(i, None)
            return httpx.Response(200, json={"results": [
                {"itemMetadata": {"id": i, "originalIndex": n, "success": True}}
                for n, i in enumerate(body["dataItemIds"])]})
        return httpx.Response(400, json={"message": f"unexpected {req.method} {path}"})

    def client(self):
        return httpx.Client(base_url=wix.API, transport=httpx.MockTransport(self.handler),
                            headers={"Authorization": "test-key", "wix-site-id": "site-1"})


@pytest.fixture()
def conn():
    from test_pipeline_db import FakeClaude, PAGE, SEED, _http, _tool_output
    from pipeline import db, runner, sources
    with db.connect(URL) as c:
        c.autocommit = True
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.autocommit = False
        db.migrate(c)
        sources.seed(c, SEED)
        runner.run(c, claude_client=FakeClaude(_tool_output()), http_client=_http([PAGE]))
        yield c


@needs_db
def test_only_published_records_reach_wix(conn):
    fake = FakeWix()
    result = wix.sync(conn, fake.client())
    assert result["fund"] == {"saved": 0, "removed": 0, "failed": []}     # still a draft
    assert set(fake.collections) == {"FilmFunds", "FilmEvents"}
    assert fake.collections["FilmFunds"]["permissions"]["read"] == "ANYONE"
    assert fake.items["FilmFunds"] == {}

    fund_id = conn.execute("SELECT id FROM funds").fetchone()["id"]
    conn.execute("UPDATE funds SET status = 'published' WHERE id = %s", (fund_id,))
    conn.commit()
    assert wix.sync(conn, fake.client(), dry_run=True)["fund"]["would_save"] == ["Documentary Development Fund"]
    assert wix.sync(conn, fake.client())["fund"]["saved"] == 1
    item = fake.items["FilmFunds"][wix.item_id("fund", fund_id)]
    assert item["title"] == "Documentary Development Fund" and item["amount"] == "GBP 25,000 - 40,000"
    assert item["nextDeadline"] == "2026-12-21" and item["displayStatus"] == "published"
    assert "Spring 2027: Round 2 (results) [expected]" in item["upcomingDates"]
    assert item["stages"] == ["development"] and item["sourceUrl"].startswith("https://funds.example.org")

    # Nothing changed: nothing is sent again.
    calls = len(fake.calls)
    assert wix.sync(conn, fake.client())["fund"]["saved"] == 0
    assert all(path != "/bulk/items/save" for _, path in fake.calls[calls:])

    # Rejected later: removed from Wix.
    conn.execute("UPDATE funds SET status = 'rejected' WHERE id = %s", (fund_id,))
    conn.commit()
    assert wix.sync(conn, fake.client())["fund"]["removed"] == 1
    assert fake.items["FilmFunds"] == {}
    assert conn.execute("SELECT wix_item_id FROM funds").fetchone()["wix_item_id"] is None


@needs_db
def test_missing_field_is_added_to_existing_collection(conn):
    fake = FakeWix()
    wix.ensure_collections(fake.client())
    fake.collections["FilmFunds"]["fields"] = [f for f in fake.collections["FilmFunds"]["fields"]
                                               if f["key"] != "applyUrl"]
    assert wix.ensure_collections(fake.client()) == ["added FilmFunds.applyUrl"]


@needs_db
def test_run_reports_wix_errors_without_failing(conn):
    from test_pipeline_db import FakeClaude, PAGE, _http, _tool_output
    from pipeline import runner
    broken = httpx.Client(base_url=wix.API, transport=httpx.MockTransport(lambda r: httpx.Response(403, text="no")))
    result = runner.run(conn, force=True, claude_client=FakeClaude(_tool_output()), http_client=_http([PAGE]),
                        wix_client=broken)
    assert "HTTP 403" in result["wix"]["error"] and result["errors"] == []
