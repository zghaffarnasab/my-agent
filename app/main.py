import asyncio
import os
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.utils import parseaddr
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup
from sqlalchemy import delete, func, select, update
from starlette.middleware.sessions import SessionMiddleware

from app import ai, board, calendar_client, config, events, filmdash, gmail_client, i18n, security, settings, siterequests, sitestats, validation
from app.version import CHANGELOG, VERSION
from app.db import BoardStatus, EventStatus, EventSuggestion, SessionLocal, Task, TaskStatus, init_db, utcnow

# Allow plain-http OAuth only for local development
if config.BASE_URL.startswith("http://localhost") or config.BASE_URL.startswith("http://127.0.0.1"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# No /docs, /redoc or /openapi.json: they would list every route to anyone, without login
app = FastAPI(title="Gmail AI Assistant", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)
HTTPS = config.BASE_URL.startswith("https://")


@app.middleware("http")
async def protect(request: Request, call_next):
    """Refuse form posts sent from other websites, and add safe headers to every answer."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and not security.same_origin(
            request.headers.get("origin"), request.headers.get("host")):
        response = Response("Forbidden", status_code=403)
    else:
        response = await call_next(request)
    for name, value in security.security_headers(HTTPS).items():
        response.headers.setdefault(name, value)
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    same_site="lax",
    https_only=HTTPS,
    max_age=60 * 60 * 24 * 7,
)
LANG_COOKIE = "lang"
TIMEZONE_CHOICES = [
    "Europe/London", "Europe/Berlin", "Europe/Paris", "Asia/Tehran", "Asia/Dubai",
    "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Tokyo", "UTC",
]


def current_lang(request: Request) -> str:
    """Language of this visitor: cookie, else the app's configured language."""
    cookie = request.cookies.get(LANG_COOKIE)
    return cookie if cookie in i18n.SUPPORTED else settings.get_language()


def i18n_context(request: Request) -> dict:
    lang = current_lang(request)
    return {
        "lang": lang,
        "dir": i18n.DIRECTION[lang],
        "t": lambda key, **params: i18n.translate(lang, key, **params),
    }


templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates"),
    context_processors=[i18n_context],
)

TABS = ("reply", "events", "other", "sent", "rejected")
TAB_STATUSES = {
    "reply": [TaskStatus.PENDING, TaskStatus.FAILED],   # a failed draft is still a reply you owe
    "other": [TaskStatus.INFO],
    "sent": [TaskStatus.SENT],
    "rejected": [TaskStatus.REJECTED],
}
HIDDEN_STATUSES = (TaskStatus.SKIPPED, TaskStatus.DELETED)   # never shown anywhere
LEGACY_STATUS_TABS = {"pending": "reply", "failed": "reply", "info": "other", "done": "other",
                      "sent": "sent", "rejected": "rejected"}   # old /?status=... links
MAX_EVENT_CARDS = 50


def fmt_date(value):
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(settings.get_timezone())).strftime("%Y-%m-%d %H:%M")


def sender_name(from_addr: str) -> str:
    name, addr = parseaddr(from_addr)
    return name or addr


def _as_date(d):
    from datetime import date as _date
    return _date.fromisoformat(d) if isinstance(d, str) else d


def _today():
    from datetime import datetime as _dt
    return _dt.now(ZoneInfo(settings.get_timezone())).date()


@pass_context
def day_heading(ctx, d):
    """'Today, Monday 05.10', 'Tomorrow, ...' or weekday + date, for the upcoming list and event cards."""
    from datetime import timedelta as _td
    lang = ctx.get("lang", "en")
    d = _as_date(d)
    weekday = i18n.translate(lang, f"weekday.{d.weekday()}")
    today = _today()
    if d == today:
        label = i18n.translate(lang, "day.today", weekday=weekday)
    elif d == today + _td(days=1):
        label = i18n.translate(lang, "day.tomorrow", weekday=weekday)
    else:
        label = weekday
    return f"{label} {d.strftime('%d.%m')}"


def is_today(d) -> bool:
    return _as_date(d) == _today()


templates.env.filters["dayhead"] = day_heading
templates.env.filters["is_today"] = is_today
templates.env.filters["dt"] = fmt_date
templates.env.filters["sender"] = sender_name
templates.env.globals["APP_VERSION"] = VERSION
templates.env.globals["film_enabled"] = filmdash.enabled
templates.env.globals["registration_mailto"] = siterequests.registration_mailto
templates.env.globals["draft_registration"] = siterequests.draft_registration
templates.env.globals["form_pack"] = siterequests.form_pack
templates.env.globals["reply_outcomes"] = validation.REPLY_OUTCOMES
templates.env.globals["update_mailto"] = siterequests.update_mailto


@app.on_event("startup")
def on_startup():
    init_db()


# ---------- Auth helpers ----------

class LoginRequired(Exception):
    pass


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse("/login", status_code=303)


def require_login(request: Request):
    # The epoch changes on "Sign out everywhere", so old cookies stop working
    if not request.session.get("auth") or request.session.get("epoch") != security.session_epoch():
        raise LoginRequired()


def flash(request: Request, key: str, kind: str = "ok", **params):
    """Store a message KEY (not text), so it is shown in the language of the next page."""
    request.session["flash"] = {"key": key, "params": {k: str(v) for k, v in params.items()}, "kind": kind}


def pop_flash(request: Request):
    return request.session.pop("flash", None)


def get_task_or_404(db, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.status in HIDDEN_STATUSES:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------- Health ----------

@app.get("/health")
def health():
    return {"ok": True, "version": VERSION}


@app.get("/changelog", response_class=HTMLResponse)
def changelog(request: Request):
    require_login(request)
    return templates.TemplateResponse(request, "changelog.html", {"changelog": CHANGELOG})


# ---------- Login ----------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    ip = _client_ip(request)
    wait = security.locked_for(ip)
    if wait:
        return templates.TemplateResponse(request, "login.html", {
            "error": "login.locked", "minutes": (wait + 59) // 60}, status_code=429)
    if secrets.compare_digest(password.encode(), config.DASHBOARD_PASSWORD.encode()):
        security.record_success(ip)
        request.session.clear()  # start a fresh session
        request.session["auth"] = True
        request.session["epoch"] = security.session_epoch()
        return RedirectResponse("/", status_code=303)
    security.record_failure(ip)
    await asyncio.sleep(1.5)  # slow down brute force
    return templates.TemplateResponse(request, "login.html", {"error": "login.error"}, status_code=401)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.post("/logout-everywhere")
def logout_everywhere(request: Request):
    require_login(request)
    security.sign_out_everywhere()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- Google OAuth ----------

@app.get("/auth/google")
def auth_google(request: Request):
    require_login(request)
    flow = gmail_client.make_flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    request.session["oauth_state"] = state
    request.session["code_verifier"] = getattr(flow, "code_verifier", None)
    return RedirectResponse(url, status_code=303)


@app.get("/auth/callback")
def auth_callback(request: Request):
    require_login(request)
    state = request.session.pop("oauth_state", None)
    if not state or request.query_params.get("state") != state:
        flash(request, "flash.gmail_connect_failed", "error")
        return RedirectResponse("/", status_code=303)

    flow = gmail_client.make_flow(state=state)
    verifier = request.session.pop("code_verifier", None)
    if verifier:
        flow.code_verifier = verifier
    flow.fetch_token(authorization_response=f"{config.BASE_URL}/auth/callback?{request.url.query}")
    creds = flow.credentials

    from googleapiclient.discovery import build
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    email = gmail_client.get_my_address(service)
    previous = gmail_client.connected_email()
    if previous and previous.lower() != email.lower():
        # Switched to another Gmail account: old tasks belong to the old mailbox and can't be sent from the new one
        with SessionLocal() as db:
            db.execute(delete(EventSuggestion))
            db.execute(delete(Task))
            db.commit()
    gmail_client.save_credentials(creds, email=email)
    flash(request, "flash.gmail_connected", email=email)
    return RedirectResponse("/", status_code=303)


# ---------- Dashboard ----------

def upcoming_suggestions(db) -> list[tuple[EventSuggestion, Task]]:
    """Suggested events that have not ended yet, from all emails, sorted by date."""
    today = _today().isoformat()
    rows = db.execute(
        select(EventSuggestion, Task)
        .join(Task, Task.id == EventSuggestion.task_id)
        .where(EventSuggestion.status == EventStatus.SUGGESTED, Task.status.not_in(HIDDEN_STATUSES))
        .order_by(EventSuggestion.date, EventSuggestion.start_time, EventSuggestion.id)
    ).all()
    return [(ev, task) for ev, task in rows if (ev.end_date or ev.date) >= today]


def _tab_of(status: str) -> tuple[str, bool]:
    """(tab, archived?) where a task with this status is listed."""
    if status == TaskStatus.DONE:
        return "other", True
    for tab, statuses in TAB_STATUSES.items():
        if status in statuses:
            return tab, False
    return "reply", False   # e.g. "sending"


def row_url(task: Task) -> str:
    """The dashboard with this task's row open. Also where a plain form post (no JavaScript) lands after an action."""
    tab, archived = _tab_of(task.status)
    return f"/?tab={tab}{'&archived=1' if archived else ''}&open={task.id}#task-{task.id}"


def _tab_counts(db, all_events) -> tuple[dict, dict]:
    counts = dict(db.execute(select(Task.status, func.count()).group_by(Task.status)).all())
    tab_counts = {
        "reply": sum(counts.get(s, 0) for s in TAB_STATUSES["reply"]),
        "events": len(all_events),
        "other": counts.get(TaskStatus.INFO, 0),
        "sent": counts.get(TaskStatus.SENT, 0),
        "rejected": counts.get(TaskStatus.REJECTED, 0),
    }
    return tab_counts, counts


def _render(request: Request, name: str, context: dict) -> str:
    """Render a template to a string (with the language helpers), for panels and row replacements."""
    return templates.TemplateResponse(request, name, context).body.decode()


def _conflicts_for(suggestions) -> dict:
    conflicts = {}
    if gmail_client.has_calendar_access():
        for sug in suggestions:
            if sug.status == EventStatus.SUGGESTED:
                try:
                    conflicts[sug.id] = calendar_client.conflicts(sug)
                except Exception:
                    conflicts[sug.id] = []
    return conflicts


def _task_panel_context(db, task: Task, back_url: str = "") -> dict:
    suggestions = db.scalars(
        select(EventSuggestion).where(EventSuggestion.task_id == task.id,
                                      EventSuggestion.status != EventStatus.DISMISSED)
        .order_by(EventSuggestion.date, EventSuggestion.start_time)
    ).all()
    return {
        "task": task,
        "suggestions": suggestions,
        "conflicts": _conflicts_for(suggestions),
        "calendar_ok": gmail_client.has_calendar_access(),
        "owner_tz": settings.get_timezone(),
        "back_url": back_url,
    }


def task_panel_html(request: Request, db, task: Task) -> Markup:
    return Markup(_render(request, "_task_panel.html", _task_panel_context(db, task)))


def event_panel_html(request: Request, db, ev: EventSuggestion) -> Markup:
    return Markup(_render(request, "_event_panel.html", {
        "ev": ev,
        "task": db.get(Task, ev.task_id),
        "conflicts": _conflicts_for([ev]),
        "calendar_ok": gmail_client.has_calendar_access(),
        "owner_tz": settings.get_timezone(),
    }))


@app.get("/", response_class=HTMLResponse)
def index(request: Request, tab: str = "", status: str = "", archived: int = 0,
          open_id: int = Query(0, alias="open")):
    require_login(request)
    if open_id and not tab and not status:       # a link like /?open=12 finds the right tab by itself
        with SessionLocal() as db:
            wanted = db.get(Task, open_id)
        if wanted is not None and wanted.status not in HIDDEN_STATUSES:
            tab, was_archived = _tab_of(wanted.status)
            archived = int(was_archived)
    tab = tab or LEGACY_STATUS_TABS.get(status, "reply")
    if tab not in TABS:
        tab = "reply"
    show_archived = bool(archived) and tab == "other"
    tasks, event_items, open_panel_html = [], [], ""
    with SessionLocal() as db:
        all_events = upcoming_suggestions(db)
        tab_counts, counts = _tab_counts(db, all_events)
        if tab == "events":
            event_items = all_events[:MAX_EVENT_CARDS]
            shown = [ev for ev, _ in event_items]
            if open_id in {ev.id for ev in shown}:
                open_panel_html = event_panel_html(request, db, next(ev for ev in shown if ev.id == open_id))
            else:
                open_id = 0
        else:
            statuses = [TaskStatus.DONE] if show_archived else TAB_STATUSES[tab]
            tasks = db.scalars(
                select(Task).where(Task.status.in_(statuses))
                # urgent mail first in the lists you still act on; archived/sent/rejected stay by date
                .order_by(*([Task.is_urgent.desc()] if tab in ("reply", "other") and not show_archived else []),
                          Task.received_at.desc().nullslast(), Task.id.desc()).limit(200)
            ).all()
            if open_id in {t.id for t in tasks}:
                open_panel_html = task_panel_html(request, db, next(t for t in tasks if t.id == open_id))
            else:
                open_id = 0
        tasks_with_events = {ev.task_id for ev, _ in all_events}
    gmail = gmail_client.connected_email()
    calendar_ok = bool(gmail) and gmail_client.has_calendar_access()
    upcoming, upcoming_error, reconnect_needed = [], None, False
    if calendar_ok:
        try:
            upcoming = calendar_client.upcoming()
        except gmail_client.ReconnectNeeded:
            reconnect_needed = True
        except Exception as exc:
            upcoming_error = str(exc)[:300]
    return templates.TemplateResponse(request, "index.html", {
        "calendar_ok": calendar_ok,
        "reconnect_needed": reconnect_needed,
        "upcoming": upcoming,
        "upcoming_error": upcoming_error,
        "upcoming_days": config.UPCOMING_DAYS,
        "tasks_with_events": tasks_with_events,
        "tasks": tasks,
        "event_items": event_items,
        "open_id": open_id,
        "open_panel_html": open_panel_html,
        "owner_tz": settings.get_timezone(),
        "tab": tab,
        "tabs": TABS,
        "tab_counts": tab_counts,
        "show_archived": show_archived,
        "archived_count": counts.get(TaskStatus.DONE, 0),
        "gmail": gmail,
        "flash": pop_flash(request),
    })


@app.post("/poll-now")
def poll_now(request: Request, background: BackgroundTasks):
    require_login(request)
    from app.worker import process_new_emails
    background.add_task(process_new_emails)
    flash(request, "flash.poll_started")
    return RedirectResponse("/", status_code=303)


@app.get("/tasks/{task_id}/panel", response_class=HTMLResponse)
def task_panel(request: Request, task_id: int):
    """The details of one row, loaded when the row is opened."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        return HTMLResponse(task_panel_html(request, db, task))


@app.get("/events/{event_id}/panel", response_class=HTMLResponse)
def event_panel(request: Request, event_id: int):
    require_login(request)
    with SessionLocal() as db:
        return HTMLResponse(event_panel_html(request, db, _get_suggestion(db, event_id)))


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    """Fallback / deep link: the same panel as in the dashboard, on its own page."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        next_task = db.scalars(
            select(Task).where(Task.status == TaskStatus.PENDING, Task.id != task_id).order_by(Task.id).limit(1)
        ).first()
        context = _task_panel_context(db, task, back_url=f"/tasks/{task_id}")
    return templates.TemplateResponse(request, "task.html", {
        **context,
        "next_task": next_task,
        "flash": pop_flash(request),
    })


# ---------- Actions: plain form posts redirect, fetch() calls get JSON ----------

def is_fetch(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "fetch"


def notify(request: Request, key: str, kind: str = "ok", **params):
    """Tell the user what happened: a flash message after a redirect, or inline text for fetch()."""
    if is_fetch(request):
        request.state.note = {"key": key, "kind": kind, "params": {k: str(v) for k, v in params.items()}}
    else:
        flash(request, key, kind, **params)


def _dest(next_url: str, task_id: int) -> str:
    """Where a plain form post goes next: the task page it came from, else the dashboard with the row open."""
    if next_url.startswith("/tasks/"):
        return _safe_next(next_url)
    with SessionLocal() as db:
        task = db.get(Task, task_id)
    return row_url(task) if task is not None else "/"


def _event_dest(next_url: str, task_id: int) -> str:
    return _safe_next(next_url) if next_url else _dest("", task_id)


def reply(request: Request, redirect_to: str, *, replace: bool = True):
    """Redirect for plain form posts. For fetch(): a small JSON answer with the new row, if it changed."""
    if not is_fetch(request):
        return RedirectResponse(redirect_to, status_code=303)

    note = getattr(request.state, "note", None)
    lang = current_lang(request)
    kind = note["kind"] if note else "ok"
    payload = {
        "ok": kind != "error",
        "kind": kind,
        "message": i18n.translate(lang, note["key"], **note["params"]) if note else "",
        "remove": False,
        "html": "",
    }
    row_kind, _, row_id = request.headers.get("x-row", "").partition(":")
    tab = request.headers.get("x-tab", "reply")
    tab = tab if tab in TABS else "reply"
    archived = request.headers.get("x-archived") == "1"
    with SessionLocal() as db:
        payload["counts"] = _tab_counts(db, upcoming_suggestions(db))[0]
        if payload["ok"] and replace and row_id.isdigit():
            if row_kind == "task":
                task = db.get(Task, int(row_id))
                statuses = [TaskStatus.DONE] if (archived and tab == "other") else TAB_STATUSES.get(tab, [])
                if task is None or task.status not in statuses:
                    payload["remove"] = True
                else:
                    payload["html"] = _render(request, "_task_row_fragment.html", {
                        "item": task, "tab": tab, "archived": archived, "is_open": True,
                        "panel_html": task_panel_html(request, db, task),
                        "has_event": any(ev.task_id == task.id for ev, _ in upcoming_suggestions(db)),
                    })
            elif row_kind == "event":
                ev = db.get(EventSuggestion, int(row_id))
                if ev is None or ev.status != EventStatus.SUGGESTED or (ev.end_date or ev.date) < _today().isoformat():
                    payload["remove"] = True
                else:
                    payload["html"] = _render(request, "_event_row_fragment.html", {
                        "ev": ev, "ev_task": db.get(Task, ev.task_id), "is_open": True,
                        "panel_html": event_panel_html(request, db, ev),
                    })
    return JSONResponse(payload)


@app.post("/tasks/{task_id}/send")
def send_task(request: Request, task_id: int, draft_body: str = Form(...), next: str = Form("")):
    require_login(request)
    if not draft_body.strip():
        notify(request, "flash.reply_empty", "error")
        return reply(request, _dest(next, task_id))

    with SessionLocal() as db:
        # Atomic claim so a double click can never send twice
        claimed = db.execute(
            update(Task)
            .where(Task.id == task_id, Task.status == TaskStatus.PENDING)
            .values(status=TaskStatus.SENDING, draft_body=draft_body)
        ).rowcount
        db.commit()
        if not claimed:
            notify(request, "flash.task_already_done", "error")
            return reply(request, _dest(next, task_id))
        task = db.get(Task, task_id)

    try:
        service = gmail_client.get_service()
        gmail_client.send_reply(
            service,
            thread_id=task.thread_id,
            to=task.reply_to,
            subject=task.subject,
            body=draft_body,
            in_reply_to=task.message_id_header,
            references=task.references_header,
        )
        try:
            gmail_client.mark_as_read(service, task.gmail_message_id)
        except Exception:
            pass
        new_status, error = TaskStatus.SENT, ""
    except Exception as exc:
        new_status, error = TaskStatus.PENDING, str(exc)

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        task.status = new_status
        task.error = error
        if new_status == TaskStatus.SENT:
            task.sent_at = utcnow()
        db.commit()

    if new_status == TaskStatus.SENT:
        found = events.extract_for_task(task, source="outgoing", text=draft_body, reference=utcnow())
        notify(request, "flash.reply_sent_with_events" if found else "flash.reply_sent")
    else:
        notify(request, "flash.send_failed", "error", error=error)
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/regenerate")
def regenerate_task(request: Request, task_id: int, instruction: str = Form(""), draft_body: str = Form(""),
                    next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
            notify(request, "flash.regen_only_pending", "error")
            return reply(request, _dest(next, task_id))
        try:
            task.draft_body = ai.draft_reply(
                from_addr=task.from_addr,
                subject=task.subject,
                body=task.original_body,
                thread_context=task.thread_context,
                previous_draft=draft_body or task.draft_body,
                instruction=instruction.strip(),
            )
            task.status = TaskStatus.PENDING
            task.error = ""
            notify(request, "flash.regen_ok")
        except Exception as exc:
            task.error = str(exc)[:2000]
            notify(request, "flash.regen_failed", "error", error=exc)
        db.commit()
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/save")
def save_task(request: Request, task_id: int, draft_body: str = Form(...), next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status in (TaskStatus.PENDING, TaskStatus.FAILED):
            task.draft_body = draft_body
            db.commit()
            notify(request, "flash.saved")
    return reply(request, _dest(next, task_id), replace=False)   # nothing else changed: keep the open row as it is


@app.post("/tasks/{task_id}/done")
def done_task(request: Request, task_id: int, next: str = Form("")):
    """Archive a mail that needs no reply. Only changes the dashboard; Gmail is not touched."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status == TaskStatus.INFO:
            task.status = TaskStatus.DONE
            db.commit()
    notify(request, "flash.marked_done")
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/undone")
def undone_task(request: Request, task_id: int, next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status == TaskStatus.DONE:
            task.status = TaskStatus.INFO
            db.commit()
    notify(request, "flash.restored_other")
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/draft-anyway")
def draft_anyway(request: Request, task_id: int, next: str = Form("")):
    """The owner wants a reply to a mail that was read as "no reply needed". The draft still waits for approval."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status not in (TaskStatus.INFO, TaskStatus.DONE):
            notify(request, "flash.task_already_done", "error")
            return reply(request, _dest(next, task_id))
        try:
            try:
                task.thread_context = gmail_client.get_thread_context(gmail_client.get_service(), task.thread_id, task.gmail_message_id)
            except Exception:   # the draft is still useful without the earlier messages
                task.thread_context = ""
            task.draft_body = ai.draft_reply(
                from_addr=task.from_addr,
                subject=task.subject,
                body=task.original_body,
                thread_context=task.thread_context,
            )
            task.status = TaskStatus.PENDING
            task.error = ""
            db.commit()
            notify(request, "flash.draft_ready")
        except Exception as exc:
            db.rollback()
            notify(request, "flash.draft_failed", "error", error=exc)
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/reject")
def reject_task(request: Request, task_id: int, next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status in (TaskStatus.PENDING, TaskStatus.FAILED):
            task.status = TaskStatus.REJECTED
            db.commit()
    notify(request, "flash.rejected")
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/restore")
def restore_task(request: Request, task_id: int, next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status == TaskStatus.REJECTED:
            task.status = TaskStatus.PENDING
            db.commit()
    return reply(request, _dest(next, task_id))


@app.post("/tasks/{task_id}/delete")
def delete_task(request: Request, task_id: int, next: str = Form("")):
    """Remove an email from the dashboard for good. Gmail is not touched.
    The row stays as an empty marker so the worker does not read (and pay for) the same email again."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status == TaskStatus.SENDING:
            notify(request, "flash.delete_busy", "error")
            return reply(request, _dest(next, task_id))
        tab, archived = _tab_of(task.status)
        db.execute(delete(EventSuggestion).where(EventSuggestion.task_id == task.id))
        task.status = TaskStatus.DELETED
        for field in ("from_addr", "reply_to", "subject", "message_id_header", "references_header", "original_body",
                      "thread_context", "draft_body", "error", "category", "summary", "original_from",
                      "original_subject", "original_date", "related_json", "action_items_json"):
            setattr(task, field, "")
        db.commit()
    notify(request, "flash.deleted")
    return reply(request, f"/?tab={tab}{'&archived=1' if archived else ''}")


# ---------- Language and settings ----------

def _safe_next(value: str) -> str:
    """Only allow redirects to a path on this site."""
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value else "/"


def _set_lang_cookie(response, lang: str):
    response.set_cookie(LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, samesite="lax",
                        httponly=True, secure=config.BASE_URL.startswith("https://"))


@app.post("/language")
def switch_language(lang: str = Form(...), next: str = Form("/")):
    response = RedirectResponse(_safe_next(next), status_code=303)
    if lang in i18n.SUPPORTED:
        _set_lang_cookie(response, lang)
    return response


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    require_login(request)
    return templates.TemplateResponse(request, "settings.html", {
        "flash": pop_flash(request),
        "app_language": settings.get_language(),
        "saved_timezone": settings.get("timezone"),
        "fallback_timezone": config.TIMEZONE,
        "timezones": TIMEZONE_CHOICES,
        "board_people": settings.get("board_people"),
    })


@app.post("/settings")
def save_settings(request: Request, language: str = Form(...), tz: str = Form(""), board_people: str = Form("")):
    require_login(request)
    tz = tz.strip()
    if language not in i18n.SUPPORTED or (tz and not settings.is_valid_timezone(tz)):
        flash(request, "flash.settings_bad_tz", "error")
        return RedirectResponse("/settings", status_code=303)
    settings.set("language", language)
    settings.set("timezone", tz)
    settings.set("board_people", board.clean_people(board_people))
    flash(request, "flash.settings_saved")
    response = RedirectResponse("/settings", status_code=303)
    _set_lang_cookie(response, language)
    return response


# ---------- Task board (/board): to-dos for the people named in Settings ----------

def _board_url(who: str, card_id: int | None = None) -> str:
    url = "/board" + (f"?who={quote(who)}" if who in board.people() else "")
    return url + (f"#card-{card_id}" if card_id else "")


def _board_reply(request: Request, ok: bool, who: str, card_id: int | None = None):
    """Drag and drop (fetch) gets a small JSON answer; plain form posts go back to the board."""
    if is_fetch(request):
        return JSONResponse({"ok": ok}, status_code=200 if ok else 400)
    if not ok:
        flash(request, "flash.board_bad", "error")
    return RedirectResponse(_board_url(who, card_id if ok else None), status_code=303)


@app.get("/board", response_class=HTMLResponse)
def board_page(request: Request, who: str = ""):
    require_login(request)
    names = board.people()
    who = who if who in names else ""
    return templates.TemplateResponse(request, "board.html", {
        "flash": pop_flash(request),
        "people": names,
        "who": who,
        "columns": board.columns(who),
        "images": board.image_ids(),
        "statuses": BoardStatus.ALL,
        "priorities": BoardStatus.PRIORITIES,
        "open_counts": board.open_counts(),
        "color_of": board.color_of,
        "today": _today().isoformat(),
    })


def _uploaded(files: list[UploadFile]) -> list[bytes]:
    """The bytes of each chosen file; a file over the size limit is cut, so board.image_type() refuses it."""
    return [data for f in files if f.filename and (data := f.file.read(board.MAX_IMAGE_BYTES + 1))]


def _saved_with_images(request: Request, card_id: int, files: list[UploadFile], done_key: str):
    skipped = board.add_images(card_id, _uploaded(files))
    if skipped:
        flash(request, "flash.board_images_skipped", "error", n=skipped)
    else:
        flash(request, done_key)


@app.post("/board/cards")
def board_create(request: Request, title: str = Form(""), notes: str = Form(""), assignee: str = Form(""),
                 due: str = Form(""), status: str = Form(BoardStatus.TODO), who: str = Form(""),
                 priority: str = Form("low"), images: list[UploadFile] = File(default=[])):
    require_login(request)
    fields = board.clean_card(title, notes, assignee, due, priority)
    card_id = board.create(fields, status) if fields else None
    if card_id:
        _saved_with_images(request, card_id, images, "flash.board_added")
    return _board_reply(request, card_id is not None, who, card_id)


@app.post("/board/cards/{card_id}/save")
def board_save(request: Request, card_id: int, title: str = Form(""), notes: str = Form(""),
               assignee: str = Form(""), due: str = Form(""), status: str = Form(""), who: str = Form(""),
               priority: str = Form("low"), images: list[UploadFile] = File(default=[]),
               remove_image: list[int] = Form(default=[])):
    require_login(request)
    fields = board.clean_card(title, notes, assignee, due, priority)
    ok = fields is not None and board.update(card_id, fields, status)
    if ok:
        board.remove_images(card_id, remove_image)
        _saved_with_images(request, card_id, images, "flash.board_saved")
    return _board_reply(request, ok, who, card_id)


@app.get("/board/images/{image_id}")
def board_image(request: Request, image_id: int):
    """A picture from a card. Its type was checked from its bytes on upload; nosniff and a sandbox keep it a picture."""
    require_login(request)
    img = board.get_image(image_id)
    if img is None:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(img.data, media_type=img.content_type, headers={
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, max-age=86400",
    })


@app.post("/board/cards/{card_id}/move")
def board_move(request: Request, card_id: int, status: str = Form(...), before: str = Form(""), who: str = Form("")):
    require_login(request)
    ok = board.move(card_id, status, int(before) if before.isdigit() else None)
    return _board_reply(request, ok, who, card_id)


@app.post("/board/cards/{card_id}/step")
def board_step(request: Request, card_id: int, direction: int = Form(...), who: str = Form("")):
    require_login(request)
    ok = direction in (-1, 1) and board.step(card_id, direction)
    return _board_reply(request, ok, who, card_id)


@app.post("/board/cards/{card_id}/delete")
def board_delete(request: Request, card_id: int, who: str = Form("")):
    require_login(request)
    ok = board.delete(card_id)
    if ok:
        flash(request, "flash.board_deleted")
    return _board_reply(request, ok, who)


# ---------- Filmmaker dashboard review (records from pipeline/) ----------

def _film_kind(kind: str) -> str:
    if kind not in filmdash.TABLES:
        raise HTTPException(status_code=404, detail="Not found")
    return kind


@app.get("/film", response_class=HTMLResponse)
def film_list(request: Request, status: str = "draft"):
    require_login(request)
    status = status if status in filmdash.STATUSES else "draft"
    context = {"flash": pop_flash(request), "status": status, "statuses": filmdash.STATUSES,
               "open_to_groups": filmdash.OPEN_TO_GROUPS, "records": [], "counts": {}, "unavailable": None}
    try:
        context["records"], context["counts"] = filmdash.overview(status)
    except filmdash.Unavailable as exc:
        context["unavailable"] = "not_configured" if str(exc) == "not configured" else "unreachable"
    return templates.TemplateResponse(request, "film_list.html", context)


@app.get("/film/{kind}/{record_id}", response_class=HTMLResponse)
def film_detail(request: Request, kind: str, record_id: int):
    require_login(request)
    try:
        rec = filmdash.get(_film_kind(kind), record_id)
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/film", status_code=303)
    if rec is None:
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse(request, "film_detail.html",
                                      {"flash": pop_flash(request), "kind": kind, "rec": rec})


@app.post("/film/{kind}/{record_id}/review")
def film_review(request: Request, kind: str, record_id: int, status: str = Form(...), note: str = Form("")):
    require_login(request)
    if status not in filmdash.STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    try:
        found = filmdash.set_status(_film_kind(kind), record_id, status, note)
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/film", status_code=303)
    if not found:
        raise HTTPException(status_code=404, detail="Not found")
    flash(request, f"flash.film_{status}")
    return RedirectResponse("/film", status_code=303)



# ---------- Website visits (/stats): anonymous page views stored by the website ----------

@app.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, days: int = 30):
    require_login(request)
    context = {"periods": sitestats.PERIODS, "s": None, "unavailable": None}
    try:
        context["s"] = sitestats.summary(days)
    except filmdash.Unavailable as exc:
        context["unavailable"] = _unavailable_key(exc)
    return templates.TemplateResponse(request, "stats.html", context)


# ---------- Website requests (/requests): match each visitor to published funds and events ----------

def _unavailable_key(exc: filmdash.Unavailable) -> str:
    return {"not configured": "not_configured", "no table": "no_table"}.get(str(exc), "unreachable")


def _to_request(request_id: int) -> RedirectResponse:
    return RedirectResponse(f"/requests/{request_id}", status_code=303)


@app.get("/requests", response_class=HTMLResponse)
def requests_list(request: Request, status: str = "matched"):
    require_login(request)
    status = status if status in siterequests.STATUSES else "matched"
    context = {"flash": pop_flash(request), "status": status, "statuses": siterequests.STATUSES,
               "rows": [], "counts": {}, "unavailable": None}
    try:
        context["rows"], context["counts"] = siterequests.overview(status)
    except filmdash.Unavailable as exc:
        context["unavailable"] = _unavailable_key(exc)
    return templates.TemplateResponse(request, "requests_list.html", context)


@app.get("/requests/{request_id}", response_class=HTMLResponse)
def request_detail(request: Request, request_id: int):
    require_login(request)
    try:
        req = siterequests.get(request_id)
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/requests", status_code=303)
    if req is None:
        raise HTTPException(status_code=404, detail="Not found")
    offer = req["profile"].get("offer") or {}
    return templates.TemplateResponse(request, "request_detail.html", {
        "flash": pop_flash(request), "req": req, "offer": offer, "statuses": siterequests.STATUSES,
        "mail_configured": siterequests.mail_configured(),
        "imap_configured": siterequests.imap_configured(), "confirm_url": siterequests.confirm_url(req["profile"]),
        "offer_mailto": siterequests.mailto(req["email"], offer.get("subject", ""), offer.get("body", "")) if offer else "",
    })


@app.get("/requests/{request_id}/files/{file_id}")
def request_file(request: Request, request_id: int, file_id: int):
    """A file the visitor attached, always as a download: the browser never shows it as a page."""
    require_login(request)
    try:
        f = siterequests.get_file(request_id, file_id)
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/requests", status_code=303)
    if f is None:
        raise HTTPException(status_code=404, detail="Not found")
    fallback = "".join(c if c.isascii() and (c.isalnum() or c in "._- ") else "_" for c in f["filename"]) or "file"
    return Response(f["data"], media_type=f["content_type"], headers={
        "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(f['filename'])}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, no-store",
    })


def _request_action(request: Request, request_id: int, action, ok_key: str):
    require_login(request)
    try:
        action()
    except siterequests.NotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/requests", status_code=303)
    flash(request, ok_key)
    return _to_request(request_id)


@app.post("/requests/{request_id}/match")
def request_match(request: Request, request_id: int):
    return _request_action(request, request_id, lambda: siterequests.match(request_id), "flash.request_matched")


@app.post("/requests/{request_id}/choose")
def request_choose(request: Request, request_id: int, keys: list[str] = Form([]), note: str = Form("")):
    return _request_action(request, request_id, lambda: siterequests.choose(request_id, keys, note),
                           "flash.request_chosen")


@app.post("/requests/{request_id}/send")
def request_send(request: Request, request_id: int, subject: str = Form(...), body: str = Form(...),
                 manual: str = Form("")):
    require_login(request)
    if not manual and not siterequests.mail_configured():
        raise HTTPException(status_code=400, detail="Mail is not configured")
    try:
        siterequests.send_offer(request_id, subject, body, manual=bool(manual))
    except siterequests.NotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/requests", status_code=303)
    except Exception as exc:
        flash(request, "flash.request_send_failed", "error", error=exc)
        return _to_request(request_id)
    flash(request, "flash.request_marked_sent" if manual else "flash.request_sent")
    return _to_request(request_id)


@app.post("/requests/{request_id}/submit")
def request_submit(request: Request, request_id: int, key: str = Form(...), subject: str = Form(...),
                   body: str = Form(...)):
    require_login(request)
    if not siterequests.mail_configured():
        raise HTTPException(status_code=400, detail="Mail is not configured")
    try:
        siterequests.send_registration(request_id, key, subject, body)
    except siterequests.NotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except filmdash.Unavailable:
        flash(request, "flash.film_unavailable", "error")
        return RedirectResponse("/requests", status_code=303)
    except Exception as exc:
        flash(request, "flash.request_send_failed", "error", error=exc)
        return _to_request(request_id)
    flash(request, "flash.request_registration_sent")
    return _to_request(request_id)


@app.post("/requests/{request_id}/registered")
def request_registered(request: Request, request_id: int, key: str = Form(...), done: str = Form("")):
    return _request_action(request, request_id, lambda: siterequests.set_registered(request_id, key, bool(done)),
                           "flash.request_updated")


@app.post("/requests/{request_id}/form-registered")
def request_form_registered(request: Request, request_id: int, key: str = Form(...), ref: str = Form(""),
                            note: str = Form("")):
    return _request_action(request, request_id,
                           lambda: siterequests.record_form_registration(request_id, key, ref, note),
                           "flash.request_updated")


@app.post("/requests/{request_id}/outcome")
def request_outcome(request: Request, request_id: int, key: str = Form(...), outcome: str = Form(...)):
    if outcome not in validation.REPLY_OUTCOMES:
        raise HTTPException(status_code=400, detail="Bad outcome")
    return _request_action(request, request_id, lambda: siterequests.set_outcome(request_id, key, outcome),
                           "flash.request_updated")


@app.post("/requests/{request_id}/status")
def request_status(request: Request, request_id: int, status: str = Form(...)):
    if status not in siterequests.STATUSES:
        raise HTTPException(status_code=400, detail="Bad status")
    return _request_action(request, request_id, lambda: siterequests.set_status(request_id, status),
                           "flash.request_updated")

# ---------- Calendar ----------

def _get_suggestion(db, event_id: int) -> EventSuggestion:
    sug = db.get(EventSuggestion, event_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return sug


@app.post("/tasks/{task_id}/find-events")
def find_events(request: Request, task_id: int, next: str = Form("")):
    """Read the email again (urgency, deadlines, events), e.g. for emails that arrived before these features existed."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
    n = events.reread_task(task) if task.original_body else 0
    if task.status == TaskStatus.SENT and task.draft_body:
        n += events.extract_for_task(task, source="outgoing", text=task.draft_body,
                                     reference=task.sent_at or utcnow())
    if n:
        notify(request, "flash.events_found", n=n)
    else:
        notify(request, "flash.events_none")
    return reply(request, _dest(next, task_id))


@app.post("/events/{event_id}/add")
def add_event(
    request: Request,
    event_id: int,
    title: str = Form(""),
    date: str = Form(...),
    end_date: str = Form(""),
    start_time: str = Form(""),
    end_time: str = Form(""),
    tz: str = Form(""),
    location: str = Form(""),
    description: str = Form(""),
    invite: str = Form(""),
    next: str = Form(""),
):
    require_login(request)
    with SessionLocal() as db:
        sug = _get_suggestion(db, event_id)
        task = db.get(Task, sug.task_id)
        if sug.status != EventStatus.SUGGESTED:
            notify(request, "flash.event_already", "error")
            return reply(request, _event_dest(next, sug.task_id))
        # apply your edits from the card
        sug.title, sug.date = title.strip(), date.strip()
        sug.end_date = validation.clean_date(end_date) if end_date.strip() > date.strip() else ""
        sug.start_time, sug.end_time = start_time.strip(), end_time.strip()
        sug.timezone = events._clean_tz(tz.strip())
        sug.location, sug.description = location.strip(), description.strip()
        try:
            duplicate = calendar_client.find_duplicate(sug)
            if duplicate:
                created, note = duplicate, "flash.event_duplicate"
            else:
                guests = gmail_client.addresses_in(task.reply_to) if (invite and task and not task.is_forward and not task.is_bulk) else None
                created = calendar_client.create_event(sug, invite=guests)
                note = "flash.event_added_invited" if guests else "flash.event_added"
            sug.status = EventStatus.ADDED
            sug.google_event_id = created.get("id", "")
            sug.html_link = created.get("htmlLink", "")
            notify(request, note)
        except Exception as exc:
            notify(request, "flash.event_add_failed", "error", error=exc)
        db.commit()
        task_id = sug.task_id
    return reply(request, _event_dest(next, task_id))


@app.post("/events/{event_id}/dismiss")
def dismiss_event(request: Request, event_id: int, next: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        sug = _get_suggestion(db, event_id)
        if sug.status == EventStatus.SUGGESTED:
            sug.status = EventStatus.DISMISSED
            db.commit()
        task_id = sug.task_id
    return reply(request, _event_dest(next, task_id))
