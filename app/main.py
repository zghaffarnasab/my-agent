import asyncio
import os
import secrets
from datetime import timezone
from zoneinfo import ZoneInfo
from email.utils import parseaddr

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, update
from starlette.middleware.sessions import SessionMiddleware

from app import ai, calendar_client, config, events, gmail_client
from app.version import CHANGELOG, VERSION
from app.db import EventStatus, EventSuggestion, SessionLocal, Task, TaskStatus, init_db, utcnow

# Allow plain-http OAuth only for local development
if config.BASE_URL.startswith("http://localhost") or config.BASE_URL.startswith("http://127.0.0.1"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

app = FastAPI(title="Gmail AI Assistant", version=VERSION)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    same_site="lax",
    https_only=config.BASE_URL.startswith("https://"),
    max_age=60 * 60 * 24 * 14,
)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

VISIBLE_STATUSES = [TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.SENT, TaskStatus.REJECTED]
STATUS_LABELS = {
    TaskStatus.PENDING: "منتظر تأیید",
    TaskStatus.FAILED: "خطا در نوشتن",
    TaskStatus.SENT: "ارسال‌شده",
    TaskStatus.REJECTED: "ردشده",
    TaskStatus.SENDING: "در حال ارسال",
}


def fmt_date(value):
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(config.TIMEZONE)).strftime("%Y-%m-%d %H:%M")


def sender_name(from_addr: str) -> str:
    name, addr = parseaddr(from_addr)
    return name or addr


FA_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def day_heading(d):
    """'امروز'، 'فردا' or weekday + date, for the upcoming list and event cards."""
    from datetime import date as _date, datetime as _dt, timedelta as _td
    if isinstance(d, str):
        d = _date.fromisoformat(d)
    today = _dt.now(ZoneInfo(config.TIMEZONE)).date()
    label = FA_WEEKDAYS[d.weekday()]
    if d == today:
        label = "امروز، " + label
    elif d == today + _td(days=1):
        label = "فردا، " + label
    return f"{label} {d.strftime('%d.%m')}"


templates.env.filters["dayhead"] = day_heading
templates.env.filters["dt"] = fmt_date
templates.env.filters["sender"] = sender_name
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS
templates.env.globals["APP_VERSION"] = VERSION


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
    if not request.session.get("auth"):
        raise LoginRequired()


def flash(request: Request, message: str, kind: str = "ok"):
    request.session["flash"] = {"message": message, "kind": kind}


def pop_flash(request: Request):
    return request.session.pop("flash", None)


def get_task_or_404(db, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.status == TaskStatus.SKIPPED:
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


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if secrets.compare_digest(password.encode(), config.DASHBOARD_PASSWORD.encode()):
        request.session["auth"] = True
        return RedirectResponse("/", status_code=303)
    await asyncio.sleep(1.5)  # slow down brute force
    return templates.TemplateResponse(request, "login.html", {"error": "رمز عبور درست نیست."}, status_code=401)


@app.post("/logout")
def logout(request: Request):
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
        flash(request, "اتصال به جیمیل ناموفق بود. دوباره امتحان کن.", "error")
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
    flash(request, f"جیمیل {email} وصل شد. ایمیل‌های جدید چند دقیقه دیگر اینجا ظاهر می‌شوند.")
    return RedirectResponse("/", status_code=303)


# ---------- Dashboard ----------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, status: str = TaskStatus.PENDING):
    require_login(request)
    if status not in VISIBLE_STATUSES:
        status = TaskStatus.PENDING
    with SessionLocal() as db:
        tasks = db.scalars(
            select(Task).where(Task.status == status).order_by(Task.received_at.desc().nullslast(), Task.id.desc()).limit(200)
        ).all()
        counts = dict(
            db.execute(
                select(Task.status, func.count()).where(Task.status.in_(VISIBLE_STATUSES)).group_by(Task.status)
            ).all()
        )
        tasks_with_events = set(db.scalars(
            select(EventSuggestion.task_id).where(EventSuggestion.status == EventStatus.SUGGESTED)
        ))
    gmail = gmail_client.connected_email()
    calendar_ok = bool(gmail) and gmail_client.has_calendar_access()
    upcoming, upcoming_error = [], None
    if calendar_ok:
        try:
            upcoming = calendar_client.upcoming()
        except Exception as exc:
            upcoming_error = str(exc)[:300]
    return templates.TemplateResponse(request, "index.html", {
        "calendar_ok": calendar_ok,
        "upcoming": upcoming,
        "upcoming_error": upcoming_error,
        "upcoming_days": config.UPCOMING_DAYS,
        "tasks_with_events": tasks_with_events,
        "tasks": tasks,
        "status": status,
        "counts": counts,
        "statuses": VISIBLE_STATUSES,
        "gmail": gmail,
        "flash": pop_flash(request),
    })


@app.post("/poll-now")
def poll_now(request: Request, background: BackgroundTasks):
    require_login(request)
    from app.worker import process_new_emails
    background.add_task(process_new_emails)
    flash(request, "بررسی صندوق شروع شد. چند ثانیه دیگر صفحه را تازه کن.")
    return RedirectResponse("/", status_code=303)


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def task_detail(request: Request, task_id: int):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        next_task = db.scalars(
            select(Task).where(Task.status == TaskStatus.PENDING, Task.id != task_id).order_by(Task.id).limit(1)
        ).first()
        suggestions = db.scalars(
            select(EventSuggestion).where(EventSuggestion.task_id == task_id,
                                          EventSuggestion.status != EventStatus.DISMISSED)
            .order_by(EventSuggestion.date, EventSuggestion.start_time)
        ).all()
    calendar_ok = gmail_client.has_calendar_access()
    conflicts = {}
    if calendar_ok:
        for sug in suggestions:
            if sug.status == EventStatus.SUGGESTED:
                try:
                    conflicts[sug.id] = calendar_client.conflicts(sug)
                except Exception:
                    conflicts[sug.id] = []
    return templates.TemplateResponse(request, "task.html", {
        "suggestions": suggestions,
        "conflicts": conflicts,
        "calendar_ok": calendar_ok,
        "owner_tz": config.TIMEZONE,
        "task": task,
        "next_task": next_task,
        "flash": pop_flash(request),
    })


@app.post("/tasks/{task_id}/send")
def send_task(request: Request, task_id: int, draft_body: str = Form(...)):
    require_login(request)
    if not draft_body.strip():
        flash(request, "متن جواب خالی است.", "error")
        return RedirectResponse(f"/tasks/{task_id}", status_code=303)

    with SessionLocal() as db:
        # Atomic claim so a double click can never send twice
        claimed = db.execute(
            update(Task)
            .where(Task.id == task_id, Task.status == TaskStatus.PENDING)
            .values(status=TaskStatus.SENDING, draft_body=draft_body)
        ).rowcount
        db.commit()
        if not claimed:
            flash(request, "این تسک قبلاً ارسال یا رد شده است.", "error")
            return RedirectResponse(f"/tasks/{task_id}", status_code=303)
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
        new_status, error = TaskStatus.PENDING, f"ارسال ناموفق: {exc}"

    with SessionLocal() as db:
        task = db.get(Task, task_id)
        task.status = new_status
        task.error = error
        if new_status == TaskStatus.SENT:
            task.sent_at = utcnow()
        db.commit()
        next_task = db.scalars(
            select(Task).where(Task.status == TaskStatus.PENDING).order_by(Task.id).limit(1)
        ).first()

    if new_status == TaskStatus.SENT:
        found = events.extract_for_task(task, source="outgoing", text=draft_body, reference=utcnow())
        if found:
            flash(request, "جواب ارسال شد. در جوابت قرار ملاقاتی پیدا شد؛ اگر خواستی به تقویم اضافه‌اش کن.")
            return RedirectResponse(f"/tasks/{task_id}#events", status_code=303)
        flash(request, "جواب ارسال شد.")
        return RedirectResponse(f"/tasks/{next_task.id}" if next_task else "/", status_code=303)
    flash(request, error, "error")
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/regenerate")
def regenerate_task(request: Request, task_id: int, instruction: str = Form(""), draft_body: str = Form("")):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status not in (TaskStatus.PENDING, TaskStatus.FAILED):
            flash(request, "فقط تسک‌های منتظر را می‌شود دوباره نوشت.", "error")
            return RedirectResponse(f"/tasks/{task_id}", status_code=303)
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
            flash(request, "پیش‌نویس تازه آماده شد.")
        except Exception as exc:
            task.error = str(exc)[:2000]
            flash(request, f"نوشتن دوباره ناموفق بود: {exc}", "error")
        db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/save")
def save_task(request: Request, task_id: int, draft_body: str = Form(...)):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status in (TaskStatus.PENDING, TaskStatus.FAILED):
            task.draft_body = draft_body
            db.commit()
            flash(request, "تغییرات ذخیره شد.")
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


@app.post("/tasks/{task_id}/reject")
def reject_task(request: Request, task_id: int):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status in (TaskStatus.PENDING, TaskStatus.FAILED):
            task.status = TaskStatus.REJECTED
            db.commit()
        next_task = db.scalars(
            select(Task).where(Task.status == TaskStatus.PENDING).order_by(Task.id).limit(1)
        ).first()
    flash(request, "تسک رد شد. ایمیل در جیمیل دست‌نخورده باقی ماند.")
    return RedirectResponse(f"/tasks/{next_task.id}" if next_task else "/", status_code=303)


@app.post("/tasks/{task_id}/restore")
def restore_task(request: Request, task_id: int):
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
        if task.status == TaskStatus.REJECTED:
            task.status = TaskStatus.PENDING
            db.commit()
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


# ---------- Calendar ----------

def _get_suggestion(db, event_id: int) -> EventSuggestion:
    sug = db.get(EventSuggestion, event_id)
    if sug is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return sug


@app.post("/tasks/{task_id}/find-events")
def find_events(request: Request, task_id: int):
    """Manually look for events, e.g. for emails that arrived before this feature existed."""
    require_login(request)
    with SessionLocal() as db:
        task = get_task_or_404(db, task_id)
    n = events.extract_for_task(task, source="incoming", text=task.original_body)
    if task.status == TaskStatus.SENT and task.draft_body:
        n += events.extract_for_task(task, source="outgoing", text=task.draft_body,
                                     reference=task.sent_at or utcnow())
    flash(request, f"{n} قرار پیدا شد." if n else "قرار تازه‌ای در این ایمیل پیدا نشد.")
    return RedirectResponse(f"/tasks/{task_id}#events", status_code=303)


@app.post("/events/{event_id}/add")
def add_event(
    request: Request,
    event_id: int,
    title: str = Form(""),
    date: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form(""),
    tz: str = Form(""),
    location: str = Form(""),
    description: str = Form(""),
    invite: str = Form(""),
):
    require_login(request)
    with SessionLocal() as db:
        sug = _get_suggestion(db, event_id)
        task = db.get(Task, sug.task_id)
        if sug.status != EventStatus.SUGGESTED:
            flash(request, "این رویداد قبلاً اضافه یا رد شده است.", "error")
            return RedirectResponse(f"/tasks/{sug.task_id}#events", status_code=303)
        # apply your edits from the card
        sug.title, sug.date = title.strip(), date.strip()
        sug.start_time, sug.end_time = start_time.strip(), end_time.strip()
        sug.timezone = events._clean_tz(tz.strip())
        sug.location, sug.description = location.strip(), description.strip()
        try:
            duplicate = calendar_client.find_duplicate(sug)
            if duplicate:
                created, note = duplicate, "این رویداد از قبل در تقویمت بود."
            else:
                guests = gmail_client.addresses_in(task.reply_to) if (invite and task) else None
                created = calendar_client.create_event(sug, invite=guests)
                note = "به تقویم اضافه شد" + (" و دعوت‌نامه ارسال شد." if guests else ".")
            sug.status = EventStatus.ADDED
            sug.google_event_id = created.get("id", "")
            sug.html_link = created.get("htmlLink", "")
            flash(request, note)
        except Exception as exc:
            flash(request, f"افزودن به تقویم ناموفق بود: {exc}", "error")
        db.commit()
        task_id = sug.task_id
    return RedirectResponse(f"/tasks/{task_id}#events", status_code=303)


@app.post("/events/{event_id}/dismiss")
def dismiss_event(request: Request, event_id: int):
    require_login(request)
    with SessionLocal() as db:
        sug = _get_suggestion(db, event_id)
        if sug.status == EventStatus.SUGGESTED:
            sug.status = EventStatus.DISMISSED
            db.commit()
        task_id = sug.task_id
    return RedirectResponse(f"/tasks/{task_id}#events", status_code=303)
