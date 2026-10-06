import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text

from app import ai, db, events

FIXTURE = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "event_invite_forward.json"), encoding="utf-8"))


def _fake_claude(payload):
    def create(**kwargs):
        _fake_claude.last = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))])
    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_warning_codes_are_validated():
    assert events._clean_warnings(["year_missing", "bogus", "location_hidden"]) == "year_missing,location_hidden"
    assert events._clean_warnings("year_missing") == ""
    assert events._clean_warnings(None) == ""


def test_prompt_asks_for_codes_not_free_text(monkeypatch):
    monkeypatch.setattr(ai, "client", _fake_claude({"events": []}))
    ai.extract_events(text=FIXTURE["body"], subject=FIXTURE["subject"], from_addr=FIXTURE["from_addr"],
                      reference=datetime(2026, 10, 5, tzinfo=timezone.utc), outgoing=False)
    system = _fake_claude.last["system"]
    for code in events.WARNING_CODES:
        assert code in system
    assert '"warnings"' in system and "ambiguity" not in system
    assert "Persian" not in system.split("written in")[0]   # no language is hardcoded; it comes from settings


def test_fixture_event_is_stored_with_valid_codes_only(monkeypatch):
    monkeypatch.setattr(ai, "client", _fake_claude(FIXTURE["model_reply"]))
    with db.SessionLocal() as s:
        task = db.Task(gmail_message_id="fixture-1", thread_id="t", from_addr=FIXTURE["from_addr"],
                       reply_to=FIXTURE["from_addr"], subject=FIXTURE["subject"], original_body=FIXTURE["body"])
        s.add(task)
        s.commit()
    assert events.extract_for_task(task, source="incoming", text=FIXTURE["body"],
                                   reference=datetime(2026, 10, 5, tzinfo=timezone.utc)) == 1
    with db.SessionLocal() as s:
        row = s.query(db.EventSuggestion).filter_by(task_id=task.id).one()
    assert row.warning_codes == ["conflicting_times", "location_hidden"]
    assert row.date == "2026-11-17" and row.start_time == "17:00" and row.timezone == "Europe/London"


def test_migration_adds_missing_column_keeps_data_and_is_repeatable(tmp_path, monkeypatch):
    old = create_engine(f"sqlite:///{tmp_path}/old.db")
    with old.begin() as c:   # the table as it was before 1.4.0 (no "warnings" column)
        c.execute(text("CREATE TABLE event_suggestions (id INTEGER PRIMARY KEY, task_id INTEGER, title VARCHAR(512), ambiguity TEXT)"))
        c.execute(text("INSERT INTO event_suggestions (id, task_id, title, ambiguity) VALUES (1, 7, 'Lunch', 'old note')"))
    monkeypatch.setattr(db, "engine", old)

    db.migrate()
    db.migrate()   # running twice must be harmless

    cols = {c["name"] for c in inspect(old).get_columns("event_suggestions")}
    assert "warnings" in cols
    with old.connect() as c:
        row = c.execute(text("SELECT title, ambiguity, warnings FROM event_suggestions")).one()
    assert tuple(row) == ("Lunch", "old note", "")


def test_migration_skips_tables_that_do_not_exist_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{tmp_path}/empty.db"))
    db.migrate()   # must not raise
