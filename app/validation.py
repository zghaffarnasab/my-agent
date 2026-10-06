"""Clean and validate everything the AI returns. Email content is untrusted, so the AI output is too.

Nothing here talks to the network: links are only checked and displayed, never opened.
"""
import re
import unicodedata
from datetime import date
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from app import settings

CATEGORIES = ("needs_reply", "event_invite", "info_fyi", "newsletter_promo", "receipt_notification", "other")

# Fixed list of warning codes the AI may return; the UI translates them (see locales/*.json).
WARNING_CODES = (
    "date_format_ambiguous", "year_missing", "timezone_guessed", "conflicting_times",
    "location_hidden", "am_pm_unclear", "multi_day_unclear",
)

MAX_EVENTS = 10
MAX_EVENT_DAYS = 31
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
# Text direction overrides can be used to make text look like something else.
_BIDI_CONTROLS = set("‪‫‬‭‮⁦⁧⁨⁩")
_TITLE_PREFIX = re.compile(
    r"^(?:\s*(?:(?:fwd?|re|invitation)\s*:|you(?:\s+are|['’]re)\s+invited\s+to\b\s*:?)\s*)+", re.I)


def clean_text(value, limit: int, multiline: bool = False) -> str:
    """Plain text only: no control or direction-override characters, capped length."""
    text = str(value if value is not None else "")
    text = "".join(
        ch for ch in text
        if ch in "\n\t" or (unicodedata.category(ch) != "Cc" and ch not in _BIDI_CONTROLS)
    )
    if multiline:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
    else:
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:limit]


def clean_title(value) -> str:
    title = _TITLE_PREFIX.sub("", clean_text(value, 300)).strip(" \"'“”‘’")
    return title[:200]


def clean_url(value) -> str:
    """Return the link if it is a plain http(s) link, else an empty string. The link is never opened."""
    raw = clean_text(value, 1024).strip("<>")
    if not raw or re.search(r"\s", raw):
        return ""
    try:
        parts = urlsplit(raw)
        host = parts.hostname
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not host or "@" in parts.netloc:
        return ""
    return raw


def url_key(value: str) -> str:
    """Normalised form of a link, for spotting the same event in several emails."""
    try:
        parts = urlsplit(value or "")
    except ValueError:
        return ""
    if not parts.netloc:
        return ""
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def title_key(value: str) -> str:
    return re.sub(r"[\W_]+", " ", (value or "").casefold()).strip()


def clean_time(value) -> str:
    m = TIME_RE.match(str(value or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def clean_tz(value) -> str:
    try:
        return ZoneInfo(str(value)).key
    except Exception:
        return settings.get_timezone()


def clean_date(value) -> str:
    try:
        d = date.fromisoformat(str(value or "").strip())
    except ValueError:
        return ""
    return d.isoformat() if 2000 <= d.year <= 2100 else ""


def clean_warnings(value) -> str:
    codes = value if isinstance(value, list) else []
    wanted = {str(x).strip() for x in codes}
    return ",".join(c for c in WARNING_CODES if c in wanted)


def clean_event(item: dict) -> dict | None:
    """One event from the AI -> safe values, or None if it has no usable date."""
    start = clean_date(item.get("date"))
    if not start:
        return None
    warnings = set(clean_warnings(item.get("warnings")).split(",")) - {""}

    end_date = clean_date(item.get("end_date"))
    if end_date:
        days = (date.fromisoformat(end_date) - date.fromisoformat(start)).days
        if days <= 0 or days > MAX_EVENT_DAYS:
            if days < 0 or days > MAX_EVENT_DAYS:
                warnings.add("multi_day_unclear")
            end_date = ""

    start_time = clean_time(item.get("start_time"))
    return {
        "title": clean_title(item.get("title")),
        "date": start,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": clean_time(item.get("end_time")) if start_time else "",
        "timezone": clean_tz(item.get("timezone")),
        "location": clean_text(item.get("location"), 500),
        "url": clean_url(item.get("url")),
        "description": clean_text(item.get("description"), 2000, multiline=True),
        "warnings": ",".join(c for c in WARNING_CODES if c in warnings),
        "cancelled": item.get("cancelled") is True,
    }


def clean_related(items) -> list[dict]:
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = clean_title(item.get("title"))
        if title:
            out.append({"title": title, "url": clean_url(item.get("url"))})
    return out[:MAX_EVENTS]


def clean_action_items(items) -> list[dict]:
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        text = clean_text(item.get("text"), 300)
        if text:
            out.append({"text": text, "due": clean_date(item.get("due"))})
    return out[:MAX_EVENTS]


def clean_classification(data, *, is_bulk: bool) -> dict:
    """Validate the whole classification answer. Raises ValueError if it is not a JSON object."""
    if not isinstance(data, dict):
        raise ValueError("The AI answer is not a JSON object")
    category = data.get("category")
    is_forward = data.get("is_forward") is True
    original = data.get("original") if isinstance(data.get("original"), dict) else {}
    raw_events = data.get("events") if isinstance(data.get("events"), list) else []
    events = [e for e in (clean_event(i) for i in raw_events if isinstance(i, dict)) if e]
    return {
        "category": category if category in CATEGORIES else "other",
        # Safety net: bulk mail and forwards never get an automatic reply draft
        "needs_reply": data.get("needs_reply") is True and not is_bulk and not is_forward,
        "summary": clean_text(data.get("summary"), 300),
        "is_forward": is_forward,
        "original_from": clean_text(original.get("from"), 500) if is_forward else "",
        "original_subject": clean_text(original.get("subject"), 500) if is_forward else "",
        "original_date": clean_text(original.get("date"), 64) if is_forward else "",
        "events": events[:MAX_EVENTS],
        "related_events": clean_related(data.get("related_events")),
        "action_items": clean_action_items(data.get("action_items")),
    }
