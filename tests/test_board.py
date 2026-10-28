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
    assert _cards()["Write the plan"].status == "blocked"
    client.post(f"/board/cards/{card_id}/step", data={"direction": "1"})
    card = _cards()["Write the plan"]
    assert card.status == "done" and card.done_at is not None
    client.post(f"/board/cards/{card_id}/step", data={"direction": "1"})   # already last: stays
    client.post(f"/board/cards/{card_id}/step", data={"direction": "-1"})
    card = _cards()["Write the plan"]
    assert card.status == "blocked" and card.done_at is None


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


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 64


def _images(card_id):
    return board.image_ids().get(card_id, [])


def test_image_type_is_read_from_the_bytes():
    assert board.image_type(PNG) == "image/png"
    assert board.image_type(JPEG) == "image/jpeg"
    assert board.image_type(b"RIFF\0\0\0\0WEBPVP8 ") == "image/webp"
    assert board.image_type(b"<svg onload=alert(1)>") == ""
    assert board.image_type(b"\x89PNG\r\n\x1a\n" + b"\0" * board.MAX_IMAGE_BYTES) == ""


def test_new_task_with_pictures_shows_them_on_the_card(client, people):
    r = client.post("/board/cards", data={"title": "With screenshot", "assignee": "Alex"},
                    files=[("images", ("shot.png", PNG, "image/png")), ("images", ("photo.jpg", JPEG, "image/jpeg"))],
                    follow_redirects=False)
    assert r.status_code == 303
    card_id = _cards()["With screenshot"].id
    ids = _images(card_id)
    assert len(ids) == 2
    page = client.get("/board").text
    assert f'src="/board/images/{ids[0]}"' in page and 'enctype="multipart/form-data"' in page
    pic = client.get(f"/board/images/{ids[0]}")
    assert pic.status_code == 200 and pic.content == PNG
    assert pic.headers["content-type"] == "image/png"
    assert pic.headers["x-content-type-options"] == "nosniff" and pic.headers["content-security-policy"] == "sandbox"


def test_files_that_are_not_pictures_are_refused(client, people):
    client.post("/board/cards", data={"title": "Bad file", "assignee": "Alex"},
                files=[("images", ("evil.png", b"<html><script>x</script>", "image/png"))], follow_redirects=False)
    card_id = _cards()["Bad file"].id
    assert _images(card_id) == []
    assert "not added" in client.get("/board").text


def test_edit_adds_and_removes_pictures_and_delete_clears_them(client, people):
    card_id = _add(client, "Pics")
    client.post(f"/board/cards/{card_id}/save", data={"title": "Pics", "assignee": "Alex"},
                files=[("images", ("a.png", PNG, "image/png")), ("images", ("b.jpg", JPEG, "image/jpeg"))])
    first, second = _images(card_id)
    client.post(f"/board/cards/{card_id}/save", data={"title": "Pics", "assignee": "Alex", "remove_image": str(first)})
    assert _images(card_id) == [second]
    client.post(f"/board/cards/{card_id}/delete", data={})
    assert board.get_image(second) is None
    assert client.get(f"/board/images/{second}").status_code == 404


def test_at_most_ten_pictures_per_task(client, people):
    card_id = _add(client, "Many")
    assert board.add_images(card_id, [PNG] * 12) == 2
    assert len(_images(card_id)) == board.MAX_IMAGES


def test_pictures_need_login(client, people):
    from fastapi.testclient import TestClient

    from app import main
    card_id = _add(client, "Private")
    board.add_images(card_id, [PNG])
    image_id = _images(card_id)[0]
    r = TestClient(main.app).get(f"/board/images/{image_id}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_priority_colors_the_card_and_defaults_to_low(client, people):
    _add(client, "Urgent one", priority="high")
    _add(client, "Soon", priority="medium")
    _add(client, "Whenever")
    _add(client, "Bogus", priority="extreme")
    cards = _cards()
    assert [cards[n].priority for n in ("Urgent one", "Soon", "Whenever", "Bogus")] == ["high", "medium", "low", "low"]
    page = client.get("/board").text
    assert f'id="card-{cards["Urgent one"].id}"' in page and "prio-high" in page and "prio-medium" in page
    assert "High priority" in page and "Medium priority" in page
    client.post(f"/board/cards/{cards['Soon'].id}/save", data={"title": "Soon", "assignee": "Alex", "priority": "low"})
    assert _cards()["Soon"].priority == "low"


def test_blocked_column_shows_what_the_task_waits_on(client, people):
    card_id = _add(client, "Sign the contract", blocked_reason="  Waiting for   the lawyer ")
    assert _cards()["Sign the contract"].blocked_reason == "Waiting for the lawyer"
    page = client.get("/board").text
    assert 'data-status="blocked"' in page and "Waiting on:" not in page   # still in To do: reason not shown
    client.post(f"/board/cards/{card_id}/move", data={"status": "blocked"}, headers=FETCH)
    page = client.get("/board").text.replace("⁨", "").replace("⁩", "")
    assert "Waiting on: Waiting for the lawyer" in page
    assert board.open_counts() == {"Alex": 1}   # blocked work is still unfinished work
