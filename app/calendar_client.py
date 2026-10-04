from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from app import config, gmail_client


def _service():
    creds = gmail_client.load_credentials()
    if creds is None:
        raise RuntimeError("Google account is not connected.")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or config.TIMEZONE)
    except Exception:
        return ZoneInfo(config.TIMEZONE)


# ---------- Reading ----------

@dataclass
class UpcomingEvent:
    title: str
    start: datetime | None     # None for all-day events
    end: datetime | None
    day: date
    all_day: bool
    location: str
    link: str


def _parse_event(item: dict, local_tz: ZoneInfo) -> UpcomingEvent:
    start, end = item.get("start", {}), item.get("end", {})
    if "dateTime" in start:
        s = datetime.fromisoformat(start["dateTime"]).astimezone(local_tz)
        e = datetime.fromisoformat(end["dateTime"]).astimezone(local_tz) if "dateTime" in end else None
        return UpcomingEvent(item.get("summary", "(بدون عنوان)"), s, e, s.date(), False,
                             item.get("location", ""), item.get("htmlLink", ""))
    d = date.fromisoformat(start["date"])
    return UpcomingEvent(item.get("summary", "(بدون عنوان)"), None, None, d, True,
                         item.get("location", ""), item.get("htmlLink", ""))


def list_events(time_min: datetime, time_max: datetime, limit: int = 100) -> list[UpcomingEvent]:
    local_tz = _tz(None)
    resp = _service().events().list(
        calendarId=config.CALENDAR_ID,
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        maxResults=limit,
    ).execute()
    return [_parse_event(item, local_tz) for item in resp.get("items", []) if item.get("status") != "cancelled"]


def upcoming(days: int | None = None) -> list[UpcomingEvent]:
    now = datetime.now(_tz(None))
    return list_events(now, now + timedelta(days=days or config.UPCOMING_DAYS))


# ---------- Writing ----------

def suggestion_window(s) -> tuple[dict, dict, datetime, datetime]:
    """Google Calendar start/end bodies plus aware datetimes, for an EventSuggestion."""
    tz = _tz(s.timezone)
    d = date.fromisoformat(s.date)
    if not s.start_time:
        return ({"date": d.isoformat()}, {"date": (d + timedelta(days=1)).isoformat()},
                datetime.combine(d, datetime.min.time(), tz),
                datetime.combine(d + timedelta(days=1), datetime.min.time(), tz))
    start = datetime.combine(d, datetime.strptime(s.start_time, "%H:%M").time(), tz)
    end = datetime.combine(d, datetime.strptime(s.end_time, "%H:%M").time(), tz) if s.end_time else None
    if end is None or end <= start:
        end = start + timedelta(hours=1)
    tzname = tz.key
    return ({"dateTime": start.replace(tzinfo=None).isoformat(), "timeZone": tzname},
            {"dateTime": end.replace(tzinfo=None).isoformat(), "timeZone": tzname},
            start, end)


def conflicts(s) -> list[UpcomingEvent]:
    """Existing events overlapping a suggestion (timed events only)."""
    if not s.start_time:
        return []
    _, _, start, end = suggestion_window(s)
    return [e for e in list_events(start, end) if not e.all_day]


def find_duplicate(s) -> dict | None:
    """An event with the same title and start already in the calendar."""
    _, _, start, end = suggestion_window(s)
    resp = _service().events().list(
        calendarId=config.CALENDAR_ID, timeMin=start.isoformat(), timeMax=end.isoformat(),
        singleEvents=True, maxResults=20,
    ).execute()
    title = (s.title or "").strip().lower()
    for item in resp.get("items", []):
        if (item.get("summary") or "").strip().lower() == title:
            return item
    return None


def create_event(s, invite: list[str] | None = None) -> dict:
    start_body, end_body, _, _ = suggestion_window(s)
    body = {
        "summary": s.title or "Meeting",
        "location": s.location or None,
        "description": s.description or None,
        "start": start_body,
        "end": end_body,
    }
    if invite:
        body["attendees"] = [{"email": e} for e in invite]
    return _service().events().insert(
        calendarId=config.CALENDAR_ID,
        body={k: v for k, v in body.items() if v is not None},
        sendUpdates="all" if invite else "none",
    ).execute()
