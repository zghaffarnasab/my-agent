import asyncio
import os
import secrets
from datetime import timezone
from email.utils import parseaddr

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, update
from starlette.middleware.sessions import SessionMiddleware

from app import ai, config, gmail_client
from app.db import SessionLocal, Task, TaskStatus, init_db, utcnow

# Allow plain-http OAuth only for local development
if config.BASE_URL.startswith("http://localhost") or config.BASE_URL.startswith("http://127.0.0.1"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

app = FastAPI(title="Gmail AI Assistant")
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
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def sender_name(from_addr: str) -> str:
    name, addr = parseaddr(from_addr)
    return name or addr


templates.env.filters["dt"] = fmt_date
templates.env.filters["sender"] = sender_name
templates.env.globals["STATUS_LABELS"] = STATUS_LABELS


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
    return {"ok": True}


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
    return templates.TemplateResponse(request, "index.html", {
        "tasks": tasks,
        "status": status,
        "counts": counts,
        "statuses": VISIBLE_STATUSES,
        "gmail": gmail_client.connected_email(),
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
    return templates.TemplateResponse(request, "task.html", {
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
