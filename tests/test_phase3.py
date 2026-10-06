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
    n = re.search(r'<span class="n">(\d+)</span>', m.group(1))
    return int(n.group(1)) if n else 0


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


def test_tab_counts_are_correct(client, world):
    html = client.get("/").text
    assert tab_count(html, "reply") == 3      # 2 pending + 1 failed draft
    assert tab_count(html, "events") == 3     # upcoming, suggested only
    assert tab_count(html, "other") == 2      # "info" only; archived mail is not counted
    assert tab_count(html, "sent") == 1
    assert tab_count(html, "rejected") == 1
    assert [m for m in re.findall(r'href="/\?tab=(\w+)"', html)] == ["reply", "events", "other", "sent", "rejected"]


def test_each_tab_lists_the_right_mail(client, world):
    reply = client.get("/?tab=reply").text
    assert "Pending one" in reply and "Pending two" in reply and "Failed one" in reply
    assert "Info one" not in reply and "Sent one" not in reply and "Skipped one" not in reply
    other = client.get("/?tab=other").text
    assert "Info one" in other and "Info two" in other
    assert "Pending one" not in other and "Done one" not in other
    assert "Sent one" in client.get("/?tab=sent").text and "Rejected one" in client.get("/?tab=rejected").text
    assert 'class="active" aria-current="page"' in client.get("/?tab=bogus").text   # unknown tab -> first tab


def test_old_status_links_still_work(client, world):
    assert "Pending one" in client.get("/?status=pending").text
    assert "Info one" in client.get("/?status=info").text
    assert "Sent one" in client.get("/?status=sent").text


def test_events_tab_is_sorted_by_date_and_complete(client, world):
    html = plain(client.get("/?tab=events").text)
    order = [html.index(t) for t in ("Running event", "Soon event", "Later event")]
    assert order == sorted(order)                                   # earliest first
    for hidden in ("Past event", "Dismissed event", "Cancelled event", "Added event"):
        assert hidden not in html
    assert html.count('class="ev-card"') == 3
    assert html.count('name="end_date"') == 3                       # every card can have an end date
    assert 'value="' + day(2) + '"' in html                         # the multi-day event keeps its end date
    assert 'value="Room 5"' in html                                 # location
    assert 'href="https://events.example.com/later" target="_blank" rel="noopener noreferrer"' in html
    assert "Conflict: you have" in html                             # calendar conflict warning
    assert "The email did not give a year" in html                  # AI warning code, translated
    assert 'name="next" value="/?tab=events"' in html
    assert "Email: Info one" in html and 'href="/tasks/%d"' % world["i1"] in html   # link back to the source email
    assert html.count('class="day-head') == 3


def test_invite_checkbox_only_for_real_correspondents(client, world):
    # "Later event" comes from a normal email -> checkbox; the other two come from a bulk mail / a plain info mail
    with SessionLocal() as db:
        db.get(Task, world["i1"]).is_forward = True
        db.commit()
    html = client.get("/?tab=events").text
    assert html.count('name="invite"') == 1          # only the event from the normal pending email (p1)


def test_other_mail_shows_summary_category_and_actions(client, world):
    html = plain(client.get("/?tab=other").text)
    assert "Summary of info one." in html and "For your information" in html and "Newsletter or promotion" in html
    assert html.count(">Done</button>") == 2 and html.count("Draft a reply anyway") == 2
    assert "Show archived mail (1)" in html
    arch = plain(client.get("/?tab=other&archived=1").text)
    assert "Archived summary." in arch and "Move back to Other mail" in arch and "Info one" not in arch
    assert "Show archived" not in arch and "Back to Other mail" in arch


def test_done_and_restore(client, world):
    r = client.post(f"/tasks/{world['i1']}/done", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?tab=other"
    with SessionLocal() as db:
        assert db.get(Task, world["i1"]).status == TaskStatus.DONE
    assert tab_count(client.get("/").text, "other") == 1
    client.post(f"/tasks/{world['i1']}/undone", follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(Task, world["i1"]).status == TaskStatus.INFO
    # only "info" mail can be archived: a draft waiting for approval is never touched
    client.post(f"/tasks/{world['p1']}/done", follow_redirects=False)
    with SessionLocal() as db:
        assert db.get(Task, world["p1"]).status == TaskStatus.PENDING
    evil = client.post(f"/tasks/{world['i2']}/done", data={"next": "//evil.example.com"}, follow_redirects=False)
    assert evil.headers["location"] == "/"


def test_draft_anyway_creates_a_draft_that_still_needs_approval(client, world, monkeypatch):
    calls = {}
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    monkeypatch.setattr(gmail_client, "get_thread_context", lambda s, t, e: "earlier")
    monkeypatch.setattr(ai, "draft_reply", lambda **kw: calls.update(kw) or "Thanks, I will look into it.")
    sent = []
    monkeypatch.setattr(gmail_client, "send_reply", lambda *a, **k: sent.append(1))
    r = client.post(f"/tasks/{world['i1']}/draft-anyway", follow_redirects=False)
    assert r.headers["location"] == f"/tasks/{world['i1']}"
    with SessionLocal() as db:
        t = db.get(Task, world["i1"])
        assert t.status == TaskStatus.PENDING and t.draft_body == "Thanks, I will look into it."
    assert calls["thread_context"] == "earlier" and sent == []          # drafted, never sent
    html = client.get("/").text
    assert tab_count(html, "reply") == 4 and tab_count(html, "other") == 1
    # a second click on a mail that already has a draft does nothing
    client.post(f"/tasks/{world['i1']}/draft-anyway", follow_redirects=False)


def test_draft_anyway_failure_keeps_the_mail_in_other_mail(client, world, monkeypatch):
    monkeypatch.setattr(gmail_client, "get_service", lambda: object())
    monkeypatch.setattr(gmail_client, "get_thread_context", lambda s, t, e: "")

    def boom(**kw):
        raise RuntimeError("api down")
    monkeypatch.setattr(ai, "draft_reply", boom)
    client.post(f"/tasks/{world['i2']}/draft-anyway", follow_redirects=False)
    with SessionLocal() as db:
        t = db.get(Task, world["i2"])
        assert t.status == TaskStatus.INFO and t.draft_body == ""
    assert "Could not write the draft: api down" in plain(client.get(f"/tasks/{world['i2']}").text)


def test_event_cards_return_to_the_events_tab(client, world, monkeypatch):
    seen = {}
    monkeypatch.setattr(calendar_client, "find_duplicate", lambda s: None)
    monkeypatch.setattr(calendar_client, "create_event", lambda s, invite=None: seen.update(invite=invite) or {"id": "g", "htmlLink": ""})
    with SessionLocal() as db:
        ev = db.query(EventSuggestion).filter_by(title="Later event").one()
        other = db.query(EventSuggestion).filter_by(title="Soon event").one()
    form = {"title": "Later event", "date": ev.date, "start_time": "10:00", "end_time": "11:00", "tz": "Europe/London",
            "location": "Room 5", "description": "", "invite": "1"}
    r = client.post(f"/events/{ev.id}/add", data=form | {"next": "/?tab=events"}, follow_redirects=False)
    assert r.headers["location"] == "/?tab=events"
    assert seen["invite"] == ["alex@example.com"]                       # normal email: invite allowed
    r = client.post(f"/events/{other.id}/dismiss", data={"next": "/?tab=events"}, follow_redirects=False)
    assert r.headers["location"] == "/?tab=events"
    assert tab_count(client.get("/").text, "events") == 1
    # no "next": back to the task page as before; an evil "next" is ignored
    with SessionLocal() as db:
        again = EventSuggestion(task_id=world["p2"], title="Third", date=day(20), timezone="UTC")
        db.add(again)
        db.commit()
    r = client.post(f"/events/{again.id}/dismiss", follow_redirects=False)
    assert r.headers["location"] == f"/tasks/{world['p2']}#events"


def test_no_invitation_is_sent_to_a_forwarder_or_a_newsletter(client, world, monkeypatch):
    seen = {}
    monkeypatch.setattr(calendar_client, "find_duplicate", lambda s: None)
    monkeypatch.setattr(calendar_client, "create_event", lambda s, invite=None: seen.update(invite=invite) or {"id": "g", "htmlLink": ""})
    with SessionLocal() as db:
        db.get(Task, world["i1"]).is_forward = True
        db.commit()
        ev = db.query(EventSuggestion).filter_by(title="Soon event").one()
    client.post(f"/events/{ev.id}/add", data={"title": "Soon", "date": ev.date, "tz": "UTC", "invite": "1"}, follow_redirects=False)
    assert seen["invite"] is None


@pytest.mark.parametrize("lang,direction", [("en", "ltr"), ("fa", "rtl")])
def test_every_tab_renders_in_both_languages(client, world, lang, direction):
    client.cookies.set("lang", lang)
    for tab in ("reply", "events", "other", "sent", "rejected"):
        r = client.get(f"/?tab={tab}")
        assert r.status_code == 200 and f'dir="{direction}"' in r.text
        assert "{{" not in r.text and "{%" not in r.text
        if lang == "en":
            assert not re.search(r"[؀-ۿ]", r.text.replace("فارسی", "")), tab
    assert client.get("/?tab=other&archived=1").status_code == 200
    assert client.get(f"/tasks/{world['i1']}").status_code == 200
    if lang == "fa":
        assert "سایر ایمیل‌ها" in client.get("/").text and "رویدادها" in client.get("/").text


def test_empty_tabs_have_helpful_messages(client):
    client.cookies.set("lang", "en")
    assert "No upcoming events were found" in client.get("/?tab=events").text
    assert "No other mail" in client.get("/?tab=other").text
    assert "No replies are waiting" in client.get("/?tab=reply").text


def test_pages_have_a_mobile_viewport_and_flexible_event_grid(client):
    html = client.get("/").text
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert "minmax(min(340px, 100%), 1fr)" in html


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


@pytest.mark.parametrize("lang", ["en", "fa"])
def test_rendered_pages_have_balanced_html(client, world, lang):
    client.cookies.set("lang", lang)
    paths = [f"/?tab={t}" for t in ("reply", "events", "other", "sent", "rejected")] + [
        "/?tab=other&archived=1", f"/tasks/{world['p1']}", f"/tasks/{world['i1']}", f"/tasks/{world['d1']}"]
    for path in paths:
        assert _unbalanced(client.get(path).text) == [], path
