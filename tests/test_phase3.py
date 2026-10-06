"""Phase 3: dashboard tabs (Needs reply | Events | Other mail | Sent | Rejected) and their actions."""
import itertools
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import ai, calendar_client, gmail_client
from app.db import EventSuggestion, SessionLocal, Task, TaskStatus

ISOLATES = re.compile("[⁦-⁩]")
_ids = itertools.count(1)
TODAY = datetime.now(ZoneInfo("Europe/London")).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def plain(html: str) -> str:
    return ISOLATES.sub("", html)


def markup(html: str) -> str:
    """The page without its <script> blocks (the script text mentions field names too)."""
    return re.sub(r"<script.*?</script>", "", html, flags=re.S)


def add_task(status, subject="Subject", **kw) -> int:
    with SessionLocal() as db:
        t = Task(gmail_message_id=f"p3-{next(_ids)}", thread_id="th", from_addr="Alex Example <alex@example.com>",
                 reply_to="alex@example.com", subject=subject, received_at=datetime.now(timezone.utc),
                 original_body="Body text", status=status, **kw)
        db.add(t)
        db.commit()
        return t.id


def add_event(task_id, title, date, **kw) -> int:
    with SessionLocal() as db:
        e = EventSuggestion(task_id=task_id, title=title, date=date, timezone="Europe/London", **kw)
        db.add(e)
        db.commit()
        return e.id


def tab_count(html: str, tab: str):
    m = re.search(rf'href="/\?tab={tab}"[^>]*>(.*?)</a>', html, re.S)
    assert m, tab
    n = re.search(r'<span class="n"([^>]*)>(\d+)</span>', m.group(1))
    return 0 if (not n or "hidden" in n.group(1)) else int(n.group(2))


@pytest.fixture()
def world():
    """A mailbox with a bit of everything."""
    ids = {
        "p1": add_task(TaskStatus.PENDING, "Pending one", draft_body="Draft one"),
        "p2": add_task(TaskStatus.PENDING, "Pending two", draft_body="Draft two"),
        "f1": add_task(TaskStatus.FAILED, "Failed one"),
        "i1": add_task(TaskStatus.INFO, "Info one", category="info_fyi", summary="Summary of info one."),
        "i2": add_task(TaskStatus.INFO, "Info two", category="newsletter_promo", summary="Summary of info two.", is_bulk=True),
        "d1": add_task(TaskStatus.DONE, "Done one", category="other", summary="Archived summary."),
        "s1": add_task(TaskStatus.SENT, "Sent one", draft_body="Sent text", sent_at=datetime.now(timezone.utc)),
        "r1": add_task(TaskStatus.REJECTED, "Rejected one"),
        "k1": add_task(TaskStatus.SKIPPED, "Skipped one"),
    }
    add_event(ids["p1"], "Later event", day(10), start_time="10:00", end_time="11:00", location="Room 5",
              url="https://events.example.com/later")
    add_event(ids["i1"], "Soon event", day(3), start_time="09:00", warnings="year_missing")
    add_event(ids["i2"], "Running event", day(-1), end_date=day(2))                        # started, still on
    add_event(ids["i2"], "Past event", day(-5))                                           # over: not shown
    add_event(ids["i1"], "Dismissed event", day(4), status="dismissed")
    add_event(ids["i1"], "Cancelled event", day(5), status="cancelled")
    add_event(ids["s1"], "Added event", day(6), status="added")
    return ids


def panel(client, task_id):
    r = client.get(f"/tasks/{task_id}/panel")
    assert r.status_code == 200
    return plain(r.text)


def event_panel(client, event_id):
    r = client.get(f"/events/{event_id}/panel")
    assert r.status_code == 200
    return plain(r.text)


def ev_id(title) -> int:
    with SessionLocal() as db:
        return db.query(EventSuggestion).filter_by(title=title).one().id


def fetch_post(client, url, data=None, *, row, tab="reply", archived=False):
    """What the dashboard JavaScript sends."""
    r = client.post(url, data=data or {}, headers={"X-Requested-With": "fetch", "X-Row": row, "X-Tab": tab,
                                                  "X-Archived": "1" if archived else "0"}, follow_redirects=False)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- tabs and counts ----------

def test_tab_counts_are_correct(client, world):
    html = client.get("/").text
    assert tab_count(html, "reply") == 3      # 2 pending + 1 failed draft
    assert tab_count(html, "events") == 3     # upcoming, suggested only
    assert tab_count(html, "other") == 2      # "info" only; archived mail is not counted
    assert tab_count(html, "sent") == 1
    assert tab_count(html, "rejected") == 1
    assert re.findall(r'href="/\?tab=(\w+)"', html) == ["reply", "events", "other", "sent", "rejected"]


def test_each_tab_lists_the_right_mail(client, world):
    reply = client.get("/?tab=reply").text
    assert "Pending one" in reply and "Pending two" in reply and "Failed one" in reply
    assert "Info one" not in reply and "Sent one" not in reply and "Skipped one" not in reply
    other = client.get("/?tab=other").text
    assert "Info one" in other and "Info two" in other and "Pending one" not in other and "Done one" not in other
    assert "Sent one" in client.get("/?tab=sent").text and "Rejected one" in client.get("/?tab=rejected").text
    assert 'class="tab on" data-tab="reply"' in client.get("/?tab=bogus").text      # unknown tab -> first tab


def test_old_status_links_still_work(client, world):
    assert "Pending one" in client.get("/?status=pending").text
    assert "Info one" in client.get("/?status=info").text
    assert "Sent one" in client.get("/?status=sent").text


# ---------- accordion rows ----------

def test_rows_are_accordions_with_accessible_buttons(client, world):
    html = markup(client.get("/?tab=reply").text)
    tid = world["p1"]
    assert re.search(rf'<button class="head" type="submit" name="open" value="{tid}" id="head-task-{tid}"\s+aria-expanded="false" aria-controls="panel-task-{tid}">', html)
    assert re.search(rf'<div class="body" id="panel-task-{tid}" role="region" aria-labelledby="head-task-{tid}" data-src="/tasks/{tid}/panel" hidden>', html)
    assert html.count('aria-expanded="true"') == 0 and html.count("<button class=\"head\"") == 3
    # collapsed header: sender, subject, date, one-line draft preview, meeting badge
    assert "Alex Example" in html and "Pending one" in html and "Draft one" in html and '<span class="mtg">Meeting</span>' in html
    assert f'href="/tasks/{tid}"' not in html                         # rows no longer navigate away
    assert 'class="ev-card"' not in html and 'name="draft_body"' not in html   # details are not in the list page


def test_no_javascript_opens_a_row_on_the_server(client, world):
    tid = world["p1"]
    html = markup(client.get(f"/?tab=reply&open={tid}").text)
    assert html.count('aria-expanded="true"') == 1 and f'id="head-task-{tid}"' in html
    assert re.search(rf'id="panel-task-{tid}"[^>]*data-loaded="1">', html) and 'name="draft_body"' in html
    assert html.count('name="draft_body"') == 1                        # only the open row has its details
    bogus = client.get("/?tab=reply&open=999999").text
    assert 'aria-expanded="true"' not in bogus
    other = client.get(f"/?open={world['i1']}").text                   # no tab: the right one is found
    assert 'class="tab on" data-tab="other"' in other and f'id="head-task-{world["i1"]}"' in other


def test_panel_order_original_then_draft_then_events(client, world):
    html = panel(client, world["p1"])
    order = [html.index(x) for x in ("Original email", "Body text", 'name="draft_body"', "Meetings and events", "Later event")]
    assert order == sorted(order)
    assert 'name="instruction"' in html and ">Rewrite</button>" in html
    for label in ("Approve and send", "Save changes", ">Reject</button>"):
        assert label in html
    assert 'formaction="/tasks/%d/save"' % world["p1"] in html and 'formaction="/tasks/%d/reject"' % world["p1"] in html
    assert "confirm(" in html                                           # sending asks first
    assert 'dir="ltr"' in html and "Alex Example" in html


def test_long_original_email_is_collapsible(client, world):
    with SessionLocal() as db:
        db.get(Task, world["p2"]).original_body = "word " * 400
        db.commit()
    html = panel(client, world["p2"])
    assert "Show the full email" in html and html.count("<details>") == 1
    assert "Show the full email" not in panel(client, world["p1"])


def test_panels_for_sent_rejected_and_other_mail(client, world):
    sent = panel(client, world["s1"])
    assert "Sent text" in sent and 'name="draft_body"' not in sent and "Put back in the queue" not in sent
    rejected = panel(client, world["r1"])
    assert "Put back in the queue" in rejected and 'name="draft_body"' not in rejected
    info = panel(client, world["i1"])
    assert "Summary of info one." in info and ">Done</button>" in info and "Draft a reply anyway" in info
    assert 'name="draft_body"' not in info
    done = panel(client, world["d1"])
    assert "Move back to Other mail" in done and ">Done</button>" not in done


def test_panel_endpoints_need_login_and_404_for_skipped(client, world):
    assert client.get(f"/tasks/{world['k1']}/panel").status_code == 404
    assert client.get("/tasks/999999/panel").status_code == 404
    from fastapi.testclient import TestClient

    from app import main
    anon = TestClient(main.app)
    r = anon.get(f"/tasks/{world['p1']}/panel", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_task_page_still_works_as_a_deep_link(client, world):
    html = client.get(f"/tasks/{world['p1']}").text
    assert 'name="draft_body"' in html and 'name="next" value="/tasks/%d"' % world["p1"] in html
    assert "data-send" in html and "Later event" in html


# ---------- Events tab ----------

def test_events_tab_rows_are_sorted_and_hide_finished_events(client, world):
    html = plain(client.get("/?tab=events").text)
    order = [html.index(t) for t in ("Running event", "Soon event", "Later event")]
    assert order == sorted(order)
    for hidden in ("Past event", "Dismissed event", "Cancelled event", "Added event"):
        assert hidden not in html
    assert html.count('<button class="head"') == 3
    assert "Room 5" in html and "Email: Pending one" in html            # location + source email in the header
    assert 'class="ev-card"' not in html                                # cards load when a row opens


def test_event_panel_is_the_editable_card(client, world):
    html = event_panel(client, ev_id("Later event"))
    assert 'name="end_date"' in html and 'value="Room 5"' in html
    assert 'href="https://events.example.com/later" target="_blank" rel="noopener noreferrer"' in html
    assert "Conflict: you have" in html and 'name="next" value="/?tab=events"' in html
    assert 'href="/?open=%d#task-%d"' % (world["p1"], world["p1"]) in html and "Email: Pending one" in html
    assert "The email did not give a year" in event_panel(client, ev_id("Soon event"))
    opened = client.get(f"/?tab=events&open={ev_id('Soon event')}").text
    assert opened.count('aria-expanded="true"') == 1 and 'class="ev-card"' in opened


def test_invite_checkbox_only_for_real_correspondents(client, world):
    assert 'name="invite"' in event_panel(client, ev_id("Later event"))              # normal pending email
    assert 'name="invite"' not in event_panel(client, ev_id("Running event"))        # from a bulk mail
    with SessionLocal() as db:
        db.get(Task, world["i1"]).is_forward = True
        db.commit()
    assert 'name="invite"' not in event_panel(client, ev_id("Soon event"))           # from a forward


# ---------- Other mail ----------

def test_other_mail_rows_show_category_and_summary(client, world):
    html = plain(client.get("/?tab=other").text)
    assert "Summary of info one." in html and "For your information" in html and "Newsletter or promotion" in html
    assert "Draft a reply anyway" not in html                           # the buttons live in the opened row
    assert "Show archived mail (1)" in html
    arch = plain(client.get("/?tab=other&archived=1").text)
    assert "Archived summary." in arch and "Info one" not in arch and "Back to Other mail" in arch


# ---------- actions without JavaScript: plain posts redirect back to the dashboard, row open ----------

def _loc(r):
    assert r.status_code == 303
    return r.headers["location"]


def test_plain_posts_land_on_the_open_row(client, world, monkeypatch):
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    sent = []
    monkeypatch.setattr(gmail_client, "send_reply", lambda *a, **k: sent.append(k))
    monkeypatch.setattr(gmail_client, "mark_as_read", lambda *a, **k: None)
    from app import events
    monkeypatch.setattr(events, "extract_for_task", lambda *a, **k: 0)
    monkeypatch.setattr(ai, "draft_reply", lambda **kw: "A new draft.")
    p1 = world["p1"]
    go = lambda path, **d: _loc(client.post(path, data=d, follow_redirects=False))

    assert go(f"/tasks/{p1}/save", draft_body="Edited") == f"/?tab=reply&open={p1}#task-{p1}"
    assert go(f"/tasks/{p1}/regenerate", draft_body="Edited", instruction="shorter") == f"/?tab=reply&open={p1}#task-{p1}"
    assert go(f"/tasks/{p1}/send", draft_body="Final text") == f"/?tab=sent&open={p1}#task-{p1}"
    assert sent and sent[0]["body"] == "Final text"
    p2 = world["p2"]
    assert go(f"/tasks/{p2}/reject") == f"/?tab=rejected&open={p2}#task-{p2}"
    assert go(f"/tasks/{p2}/restore") == f"/?tab=reply&open={p2}#task-{p2}"
    i1 = world["i1"]
    assert go(f"/tasks/{i1}/done") == f"/?tab=other&archived=1&open={i1}#task-{i1}"
    assert go(f"/tasks/{i1}/undone") == f"/?tab=other&open={i1}#task-{i1}"
    assert go(f"/tasks/{i1}/draft-anyway") == f"/?tab=reply&open={i1}#task-{i1}"
    assert go(f"/tasks/{p2}/find-events") == f"/?tab=reply&open={p2}#task-{p2}"
    # the redirect target opens the row: the full no-JavaScript round trip
    assert 'aria-expanded="true"' in client.get(f"/?tab=sent&open={p1}").text


def test_plain_post_flash_message_is_shown_once_on_the_next_page(client, world, monkeypatch):
    monkeypatch.setattr(ai, "draft_reply", lambda **kw: "New.")
    p1 = world["p1"]
    client.post(f"/tasks/{p1}/regenerate", data={"draft_body": "x", "instruction": "y"}, follow_redirects=False)
    assert "A new draft is ready." in plain(client.get(f"/?tab=reply&open={p1}").text)
    assert "A new draft is ready." not in plain(client.get(f"/?tab=reply&open={p1}").text)


def test_the_task_page_keeps_its_own_redirects(client, world, monkeypatch):
    p1 = world["p1"]
    r = client.post(f"/tasks/{p1}/save", data={"draft_body": "x", "next": f"/tasks/{p1}"}, follow_redirects=False)
    assert _loc(r) == f"/tasks/{p1}"
    r = client.post(f"/tasks/{p1}/save", data={"draft_body": "x", "next": "//evil.example.com"}, follow_redirects=False)
    assert _loc(r) == f"/?tab=reply&open={p1}#task-{p1}"


def test_event_cards_return_to_the_events_tab_or_the_row(client, world, monkeypatch):
    seen = {}
    monkeypatch.setattr(calendar_client, "find_duplicate", lambda s: None)
    monkeypatch.setattr(calendar_client, "create_event", lambda s, invite=None: seen.update(invite=invite) or {"id": "g", "htmlLink": ""})
    ev, other = ev_id("Later event"), ev_id("Soon event")
    form = {"title": "Later event", "date": day(10), "start_time": "10:00", "end_time": "11:00", "tz": "Europe/London",
            "location": "Room 5", "description": "", "invite": "1"}
    r = client.post(f"/events/{ev}/add", data=form | {"next": "/?tab=events"}, follow_redirects=False)
    assert _loc(r) == "/?tab=events" and seen["invite"] == ["alex@example.com"]
    assert _loc(client.post(f"/events/{other}/dismiss", data={"next": "/?tab=events"}, follow_redirects=False)) == "/?tab=events"
    assert tab_count(client.get("/").text, "events") == 1
    with SessionLocal() as db:
        again = EventSuggestion(task_id=world["p2"], title="Third", date=day(20), timezone="UTC")
        db.add(again)
        db.commit()
    p2 = world["p2"]
    assert _loc(client.post(f"/events/{again.id}/dismiss", follow_redirects=False)) == f"/?tab=reply&open={p2}#task-{p2}"
    assert _loc(client.post(f"/events/{again.id}/dismiss", data={"next": "//evil.example.com"}, follow_redirects=False)) == "/"


def test_no_invitation_is_sent_to_a_forwarder_or_a_newsletter(client, world, monkeypatch):
    seen = {}
    monkeypatch.setattr(calendar_client, "find_duplicate", lambda s: None)
    monkeypatch.setattr(calendar_client, "create_event", lambda s, invite=None: seen.update(invite=invite) or {"id": "g", "htmlLink": ""})
    with SessionLocal() as db:
        db.get(Task, world["i1"]).is_forward = True
        db.commit()
    ev = ev_id("Soon event")
    client.post(f"/events/{ev}/add", data={"title": "Soon", "date": day(3), "tz": "UTC", "invite": "1"}, follow_redirects=False)
    assert seen["invite"] is None


# ---------- actions with JavaScript: fetch() gets JSON, the row updates in place ----------

def test_fetch_send_removes_the_row_and_updates_the_counts(client, world, monkeypatch):
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    monkeypatch.setattr(gmail_client, "send_reply", lambda *a, **k: None)
    monkeypatch.setattr(gmail_client, "mark_as_read", lambda *a, **k: None)
    from app import events
    monkeypatch.setattr(events, "extract_for_task", lambda *a, **k: 0)
    res = fetch_post(client, f"/tasks/{world['p1']}/send", {"draft_body": "Hello"}, row=f"task:{world['p1']}")
    assert res["ok"] and res["remove"] and res["message"] == "Reply sent." and res["html"] == ""
    assert res["counts"]["reply"] == 2 and res["counts"]["sent"] == 2
    assert "Reply sent." not in client.get("/").text                   # nothing was left in the session for the next page


def test_fetch_errors_keep_the_row_and_the_typed_text(client, world):
    res = fetch_post(client, f"/tasks/{world['p1']}/send", {"draft_body": "   "}, row=f"task:{world['p1']}")
    assert res["ok"] is False and res["kind"] == "error" and res["message"] == "The reply is empty."
    assert res["html"] == "" and res["remove"] is False                 # the page keeps the row as it is
    client.cookies.set("lang", "fa")
    res = fetch_post(client, f"/tasks/{world['p1']}/send", {"draft_body": ""}, row=f"task:{world['p1']}")
    assert res["message"] == "متن جواب خالی است."


def test_fetch_save_changes_nothing_else_and_regenerate_returns_the_new_row(client, world, monkeypatch):
    monkeypatch.setattr(ai, "draft_reply", lambda **kw: "Shorter draft.")
    p1 = world["p1"]
    saved = fetch_post(client, f"/tasks/{p1}/save", {"draft_body": "My edit"}, row=f"task:{p1}")
    assert saved["ok"] and saved["html"] == "" and saved["message"] == "Changes saved."
    new = fetch_post(client, f"/tasks/{p1}/regenerate", {"draft_body": "My edit", "instruction": "shorter"}, row=f"task:{p1}")
    assert new["ok"] and not new["remove"] and "Shorter draft." in new["html"]
    assert new["html"].lstrip().startswith(f'<li class="row open" id="task-{p1}"')
    assert 'aria-expanded="true"' in new["html"] and _unbalanced(new["html"]) == []


def test_fetch_actions_move_rows_between_tabs(client, world, monkeypatch):
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    monkeypatch.setattr(gmail_client, "get_thread_context", lambda s, t, e: "")
    monkeypatch.setattr(ai, "draft_reply", lambda **kw: "Draft.")
    res = fetch_post(client, f"/tasks/{world['p2']}/reject", row=f"task:{world['p2']}")
    assert res["remove"] and res["counts"]["reply"] == 2 and res["counts"]["rejected"] == 2
    res = fetch_post(client, f"/tasks/{world['i1']}/done", row=f"task:{world['i1']}", tab="other")
    assert res["remove"] and res["counts"]["other"] == 1
    res = fetch_post(client, f"/tasks/{world['d1']}/undone", row=f"task:{world['d1']}", tab="other", archived=True)
    assert res["remove"] and res["counts"]["other"] == 2
    res = fetch_post(client, f"/tasks/{world['i2']}/draft-anyway", row=f"task:{world['i2']}", tab="other")
    assert res["remove"] and res["message"].startswith("A reply draft is ready")
    res = fetch_post(client, f"/tasks/{world['r1']}/restore", row=f"task:{world['r1']}", tab="rejected")
    assert res["remove"]


def test_fetch_event_actions_update_the_task_row_or_remove_the_event_row(client, world, monkeypatch):
    monkeypatch.setattr(calendar_client, "find_duplicate", lambda s: None)
    monkeypatch.setattr(calendar_client, "create_event", lambda s, invite=None: {"id": "g", "htmlLink": "https://calendar.example/g"})
    form = {"title": "Later event", "date": day(10), "start_time": "10:00", "end_time": "11:00", "tz": "Europe/London", "location": "Room 5"}
    in_task = fetch_post(client, f"/events/{ev_id('Later event')}/add", form, row=f"task:{world['p1']}")
    assert in_task["ok"] and not in_task["remove"] and "Added to the calendar" in in_task["html"]
    assert in_task["message"] == "Added to the calendar." and in_task["counts"]["events"] == 2
    in_events = fetch_post(client, f"/events/{ev_id('Soon event')}/dismiss", row=f"event:{ev_id('Soon event')}", tab="events")
    assert in_events["remove"] and in_events["counts"]["events"] == 1
    again = fetch_post(client, f"/events/{ev_id('Soon event')}/add", form, row=f"event:{ev_id('Soon event')}", tab="events")
    assert again["ok"] is False and again["message"] == "This event was already added or dismissed."


def test_fetch_requires_login(world):
    from fastapi.testclient import TestClient

    from app import main
    r = TestClient(main.app).post(f"/tasks/{world['p1']}/save", data={"draft_body": "x"},
                                  headers={"X-Requested-With": "fetch"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# ---------- both languages, both directions ----------

@pytest.mark.parametrize("lang,direction", [("en", "ltr"), ("fa", "rtl")])
def test_every_tab_and_panel_renders_in_both_languages(client, world, lang, direction):
    client.cookies.set("lang", lang)
    pages = [f"/?tab={t}" for t in ("reply", "events", "other", "sent", "rejected")] + [
        "/?tab=other&archived=1", f"/?open={world['p1']}", f"/tasks/{world['i1']}", f"/tasks/{world['p1']}/panel",
        f"/events/{ev_id('Later event')}/panel"]
    for path in pages:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "{{" not in r.text and "{%" not in r.text
        if "panel" not in path:
            assert f'<html lang="{lang}" dir="{direction}">' in r.text
        if lang == "en":
            assert not re.search(r"[؀-ۿ]", r.text.replace("فارسی", "")), path
    if lang == "fa":
        assert "تأیید و ارسال" in client.get(f"/tasks/{world['p1']}/panel").text


def test_times_and_dates_stay_left_to_right(client, world):
    client.cookies.set("lang", "fa")
    html = client.get("/?tab=events").text
    assert re.search(r'<span class="date" dir="ltr">\d{4}-\d{2}-\d{2}', html)
    assert 'dir="ltr">' in client.get("/?tab=reply").text
    assert '<input type="time" dir="ltr"' in client.get(f"/events/{ev_id('Later event')}/panel").text


def test_empty_tabs_have_helpful_messages(client):
    client.cookies.set("lang", "en")
    assert "No upcoming events were found" in client.get("/?tab=events").text
    assert "No other mail" in client.get("/?tab=other").text
    assert "No replies are waiting" in client.get("/?tab=reply").text


def test_pages_have_a_mobile_viewport_and_flexible_event_grid(client):
    html = client.get("/").text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert "minmax(min(340px, 100%), 1fr)" in html


def test_dashboard_is_a_narrow_single_column(client):
    assert 'class="wrap narrow"' in client.get("/").text
    assert ".wrap.narrow { max-width: 820px; }" in client.get("/").text


@pytest.mark.parametrize("lang", ["en", "fa"])
def test_rendered_pages_have_balanced_html(client, world, lang):
    client.cookies.set("lang", lang)
    paths = [f"/?tab={t}" for t in ("reply", "events", "other", "sent", "rejected")] + [
        "/?tab=other&archived=1", f"/?open={world['p1']}", f"/?open={world['i1']}", f"/tasks/{world['p1']}",
        f"/tasks/{world['i1']}", f"/tasks/{world['d1']}"]
    for path in paths:
        assert _unbalanced(client.get(path).text) == [], path
    for path in (f"/tasks/{world['p1']}/panel", f"/tasks/{world['s1']}/panel", f"/tasks/{world['r1']}/panel",
                 f"/events/{ev_id('Later event')}/panel"):
        assert _unbalanced(client.get(path).text) == [], path


VOID = {"meta", "link", "input", "br", "hr", "img", "option"}


def _unbalanced(html: str) -> list[str]:
    from html.parser import HTMLParser

    problems, stack = [], []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in VOID:
                stack.append(tag)

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if not stack or stack[-1] != tag:
                problems.append(f"</{tag}> closes {stack[-1] if stack else 'nothing'}")
            else:
                stack.pop()

    P().feed(html)
    return problems + [f"<{t}> never closed" for t in stack]


