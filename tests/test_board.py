import re

import pytest

from app import board, settings
from app.db import BoardCard, SessionLocal

FETCH = {"X-Requested-With": "fetch"}


@pytest.fixture()
def people():
    settings.set("board_people", "Alex, Sam")
    yield ["Alex", "Sam"]
    settings.set("board_people", "")


def _cards():
    with SessionLocal() as db:
        return {c.title: c for c in db.query(BoardCard).all()}


def _add(client, title, assignee="Alex", **extra):
    r = client.post("/board/cards", data={"title": title, "assignee": assignee, **extra}, follow_redirects=False)
    assert r.status_code == 303
    return _cards()[title].id


def test_people_are_cleaned_and_persian_comma_counts():
    assert board.clean_people(" Alex ،Sam, alex,, Kim ") == "Alex, Sam, Kim"


def test_board_asks_for_people_first(client):
    r = client.get("/board")
    assert r.status_code == 200 and 'href="/settings"' in r.text
    assert client.post("/board/cards", data={"title": "x", "assignee": "Alex"}, follow_redirects=False).status_code == 303
    assert _cards() == {}


def test_settings_page_saves_board_people(client):
    client.post("/settings", data={"language": "en", "tz": "", "board_people": "Alex,  Sam ,Alex"})
    try:
        assert board.people() == ["Alex", "Sam"]
        assert 'value="Alex, Sam"' in client.get("/settings").text
    finally:
        settings.set("board_people", "")


def test_create_shows_owner_and_filters_by_person(client, people):
    _add(client, "Book the venue", "Alex", due="2026-12-01", notes="call first")
    _add(client, "Send the script", "Sam")
    page = client.get("/board").text
    assert "Book the venue" in page and "Send the script" in page
    assert 'title="Owner: Alex"' in page.replace("⁨", "").replace("⁩", "")
    assert "2026-12-01" in page
    only_sam = client.get("/board?who=Sam").text
    assert "Send the script" in only_sam and "Book the venue" not in only_sam
    assert "Book the venue" in client.get("/board?who=Nobody").text   # an unknown name shows everyone


def test_create_rejects_empty_title_and_unknown_owner(client, people):
    client.post("/board/cards", data={"title": "  ", "assignee": "Alex"})
    client.post("/board/cards", data={"title": "Ghost", "assignee": "Mallory"})
    assert _cards() == {}


def test_step_moves_between_columns_and_sets_done_time(client, people):
    card_id = _add(client, "Write the plan")
    client.post(f"/board/cards/{card_id}/step", data={"direction": "1"})
    client.post(f"/board/cards/{card_id}/step", data={"direction": "1"})
    card = _cards()["Write the plan"]
    assert card.status == "done" and card.done_at is not None
    client.post(f"/board/cards/{card_id}/step", data={"direction": "1"})   # already last: stays
    client.post(f"/board/cards/{card_id}/step", data={"direction": "-1"})
    card = _cards()["Write the plan"]
    assert card.status == "doing" and card.done_at is None


def test_drag_and_drop_move_orders_the_column(client, people):
    a, b, c = (_add(client, n) for n in ("A", "B", "C"))
    r = client.post(f"/board/cards/{c}/move", data={"status": "todo", "before": str(a)}, headers=FETCH)
    assert r.json() == {"ok": True}
    assert [x.title for x in board.columns()["todo"]] == ["C", "A", "B"]
    client.post(f"/board/cards/{a}/move", data={"status": "doing", "before": ""}, headers=FETCH)
    cols = board.columns()
    assert [x.title for x in cols["todo"]] == ["C", "B"] and [x.title for x in cols["doing"]] == ["A"]
    assert client.post(f"/board/cards/{a}/move", data={"status": "bogus"}, headers=FETCH).status_code == 400


def test_edit_and_delete(client, people):
    card_id = _add(client, "Draft")
    client.post(f"/board/cards/{card_id}/save",
                data={"title": "Final", "assignee": "Sam", "due": "not-a-date", "notes": "n", "status": "done"})
    card = _cards()["Final"]
    assert (card.assignee, card.due, card.status, card.notes) == ("Sam", "", "done", "n")
    client.post(f"/board/cards/{card_id}/delete", data={})
    assert _cards() == {}


def test_overdue_card_is_marked(client, people):
    _add(client, "Late one", due="2020-01-01")
    assert 'class="due late"' in client.get("/board").text


@pytest.mark.parametrize("lang,direction", [("en", "ltr"), ("fa", "rtl")])
def test_board_renders_in_both_languages_and_is_in_the_menu(client, people, lang, direction):
    _add(client, "Something")
    client.cookies.set("lang", lang)
    r = client.get("/board")
    assert r.status_code == 200 and f'dir="{direction}"' in r.text
    assert "{{" not in r.text and "{%" not in r.text
    assert re.search(r'<a href="/board" class="on" aria-current="page">', r.text)
    if lang == "en":
        assert not re.search(r"[؀-ۿ]", r.text.replace("فارسی", ""))


def test_board_needs_login():
    from fastapi.testclient import TestClient

    from app import main
    r = TestClient(main.app).get("/board", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
