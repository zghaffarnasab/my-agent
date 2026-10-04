import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value or ""


# --- Web app ---
BASE_URL = _get("BASE_URL", "http://localhost:8000").rstrip("/")
SECRET_KEY = _get("SECRET_KEY", required=True)          # for signing session cookies
DASHBOARD_PASSWORD = _get("DASHBOARD_PASSWORD", required=True)

# --- Database ---
DATABASE_URL = _get("DATABASE_URL", "sqlite:////data/app.db")

# --- Google OAuth (Web application client) ---
GOOGLE_CLIENT_ID = _get("GOOGLE_CLIENT_ID", required=True)
GOOGLE_CLIENT_SECRET = _get("GOOGLE_CLIENT_SECRET", required=True)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"          # read + label + send
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"    # read + create events
GMAIL_SCOPES = [GMAIL_SCOPE, CALENDAR_SCOPE]  # everything requested when connecting

# --- Anthropic ---
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY", required=True)
CLAUDE_MODEL = _get("CLAUDE_MODEL", "claude-sonnet-5-5")

# --- Calendar ---
TIMEZONE = _get("TIMEZONE", "Europe/Berlin")   # your own time zone (IANA name)
CALENDAR_ID = _get("CALENDAR_ID", "primary")
UPCOMING_DAYS = int(_get("UPCOMING_DAYS", "7"))

# --- Worker ---
POLL_INTERVAL_SECONDS = int(_get("POLL_INTERVAL_SECONDS", "180"))
# Gmail search query for emails that should get a draft reply
GMAIL_QUERY = _get(
    "GMAIL_QUERY",
    "in:inbox is:unread newer_than:2d -category:promotions -category:social -category:updates -category:forums",
)
MAX_EMAILS_PER_RUN = int(_get("MAX_EMAILS_PER_RUN", "20"))

# --- Reply personalization ---
OWNER_NAME = _get("OWNER_NAME", "")
REPLY_STYLE = _get(
    "REPLY_STYLE",
    "Polite, clear and concise. Professional but warm.",
)
EMAIL_SIGNATURE = _get("EMAIL_SIGNATURE", "")
