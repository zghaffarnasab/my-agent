import base64
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app import config
from app.db import GoogleCredential, SessionLocal

AUTO_SENDER_PATTERN = re.compile(
    r"(no-?reply|do-?not-?reply|mailer-daemon|postmaster|notifications?@|bounce)", re.I
)


# ---------- OAuth ----------

def make_flow(state: str | None = None) -> Flow:
    client_config = {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=config.GMAIL_SCOPES,
        state=state,
        redirect_uri=f"{config.BASE_URL}/auth/callback",
    )


def save_credentials(creds: Credentials, email: str | None = None) -> None:
    with SessionLocal() as db:
        row = db.get(GoogleCredential, 1)
        if row is None:
            row = GoogleCredential(id=1, token_json=creds.to_json(), email=email or "")
            db.add(row)
        else:
            row.token_json = creds.to_json()
            if email:
                row.email = email
        db.commit()


def load_credentials() -> Credentials | None:
    with SessionLocal() as db:
        row = db.get(GoogleCredential, 1)
        if row is None:
            return None
        creds = Credentials.from_authorized_user_info(json.loads(row.token_json), config.GMAIL_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)
    return creds


def connected_email() -> str | None:
    with SessionLocal() as db:
        row = db.get(GoogleCredential, 1)
        return row.email if row else None


def get_service():
    creds = load_credentials()
    if creds is None:
        raise RuntimeError("Gmail is not connected yet. Open the dashboard and connect your account.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------- Parsing ----------

@dataclass
class ParsedEmail:
    id: str
    thread_id: str
    from_addr: str
    reply_to: str
    to: str
    cc: str
    subject: str
    message_id_header: str
    references_header: str
    received_at: datetime | None
    body: str
    is_bulk: bool  # newsletters, mailing lists, automated senders


def _headers(payload: dict) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def _extract_body(payload: dict) -> str:
    """Prefer text/plain; fall back to text/html converted to text."""
    plain, htm = [], []

    def walk(part: dict):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            htm.append(_decode(data))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain).strip()
    if htm:
        return _html_to_text("\n".join(htm))
    return ""


def _strip_quoted(text: str) -> str:
    """Remove the quoted previous conversation at the bottom of a reply."""
    lines = []
    for line in text.splitlines():
        if re.match(r"^\s*On .+ wrote:\s*$", line) or re.match(r"^-{2,}\s*Original Message", line, re.I):
            break
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def parse_message(msg: dict) -> ParsedEmail:
    payload = msg["payload"]
    h = _headers(payload)
    received = None
    if msg.get("internalDate"):
        received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)

    from_addr = h.get("from", "")
    sender_email = parseaddr(from_addr)[1]
    is_bulk = bool(
        h.get("list-unsubscribe")
        or h.get("list-id")
        or h.get("precedence", "").lower() in ("bulk", "list", "junk")
        or h.get("auto-submitted", "no").lower() != "no"
        or AUTO_SENDER_PATTERN.search(sender_email)
    )

    return ParsedEmail(
        id=msg["id"],
        thread_id=msg["threadId"],
        from_addr=from_addr,
        reply_to=h.get("reply-to") or from_addr,
        to=h.get("to", ""),
        cc=h.get("cc", ""),
        subject=h.get("subject", ""),
        message_id_header=h.get("message-id", ""),
        references_header=h.get("references", ""),
        received_at=received,
        body=_strip_quoted(_extract_body(payload))[:15000],
        is_bulk=is_bulk,
    )


# ---------- Reading ----------

def get_my_address(service) -> str:
    return service.users().getProfile(userId="me").execute()["emailAddress"]


def list_candidate_message_ids(service, query: str, limit: int) -> list[str]:
    resp = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    return [m["id"] for m in resp.get("messages", [])]


def get_message(service, message_id: str) -> ParsedEmail:
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    return parse_message(msg)


def get_thread_context(service, thread_id: str, exclude_id: str, max_messages: int = 5) -> str:
    """Previous messages of the thread, oldest first, as plain text for the AI."""
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    parts = []
    for m in thread.get("messages", []):
        if m["id"] == exclude_id:
            continue
        p = parse_message(m)
        parts.append(f"From: {p.from_addr}\nSubject: {p.subject}\n\n{p.body[:3000]}")
    return "\n\n---\n\n".join(parts[-max_messages:])


# ---------- Sending ----------

def send_reply(service, *, thread_id: str, to: str, subject: str, body: str,
               in_reply_to: str, references: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = f"{references} {in_reply_to}".strip()
    msg.set_content(body)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": thread_id}
    ).execute()
    return sent["id"]


def mark_as_read(service, message_id: str) -> None:
    service.users().messages().modify(
        userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def addresses_in(header_value: str) -> list[str]:
    return [addr.lower() for _, addr in getaddresses([header_value]) if addr]
