from datetime import datetime, timezone

import logging

import json

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL

log = logging.getLogger(__name__)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TaskStatus:
    PENDING = "pending"      # draft ready, waiting for your review
    SENDING = "sending"      # being sent right now
    SENT = "sent"
    REJECTED = "rejected"
    FAILED = "failed"        # AI draft failed; can be regenerated
    SKIPPED = "skipped"      # own / empty / system mail, or bulk mail we chose not to read; never shown
    INFO = "info"            # read and summarised, no reply needed ("Other mail"); never uses "pending"
    DONE = "done"            # an INFO mail the owner has archived
    DELETED = "deleted"      # removed by the owner; content wiped, row kept so the worker never reads the mail again


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gmail_message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)

    from_addr: Mapped[str] = mapped_column(String(512))
    reply_to: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(1024), default="")
    message_id_header: Mapped[str] = mapped_column(String(1024), default="")
    references_header: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    original_body: Mapped[str] = mapped_column(Text, default="")
    thread_context: Mapped[str] = mapped_column(Text, default="")
    draft_body: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.PENDING, index=True)
    error: Mapped[str] = mapped_column(Text, default="")

    # Filled by the classification step (empty for emails read before 1.5.0)
    category: Mapped[str] = mapped_column(String(32), default="")
    needs_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    is_bulk: Mapped[bool] = mapped_column(Boolean, default=False)
    is_forward: Mapped[bool] = mapped_column(Boolean, default=False)
    original_from: Mapped[str] = mapped_column(String(512), default="")      # of a forwarded message
    original_subject: Mapped[str] = mapped_column(String(1024), default="")
    original_date: Mapped[str] = mapped_column(String(64), default="")
    related_json: Mapped[str] = mapped_column(Text, default="")              # [{"title", "url"}], no dates
    action_items_json: Mapped[str] = mapped_column(Text, default="")         # [{"text", "due"}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def related(self) -> list[dict]:
        return _json_list(self.related_json)

    @property
    def action_items(self) -> list[dict]:
        return _json_list(self.action_items_json)


def _json_list(raw: str) -> list[dict]:
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


class EventStatus:
    SUGGESTED = "suggested"
    ADDED = "added"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"    # the email says the event was cancelled; shown, but cannot be added


class EventSuggestion(Base):
    """A meeting/appointment found in an email, waiting for you to add it to Google Calendar."""
    __tablename__ = "event_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="incoming")   # incoming | outgoing

    title: Mapped[str] = mapped_column(String(512), default="")
    date: Mapped[str] = mapped_column(String(10), default="")             # YYYY-MM-DD (first day)
    end_date: Mapped[str] = mapped_column(String(10), default="")         # last day of a multi-day event, else empty
    start_time: Mapped[str] = mapped_column(String(5), default="")        # HH:MM, empty = all-day
    end_time: Mapped[str] = mapped_column(String(5), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")            # invite / registration link (display only)
    description: Mapped[str] = mapped_column(Text, default="")
    ambiguity: Mapped[str] = mapped_column(Text, default="")              # legacy free text (before 1.4.0)
    warnings: Mapped[str] = mapped_column(Text, default="")               # comma-separated warning codes

    status: Mapped[str] = mapped_column(String(16), default=EventStatus.SUGGESTED, index=True)
    google_event_id: Mapped[str] = mapped_column(String(256), default="")
    html_link: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def warning_codes(self) -> list[str]:
        return [c for c in (self.warnings or "").split(",") if c]


class GoogleCredential(Base):
    """Single row (id=1) holding the OAuth token of the connected Gmail account."""
    __tablename__ = "google_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(512), default="")
    token_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Setting(Base):
    """Simple key/value settings edited on the Settings page (language, time zone)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


# Columns added after the first release. create_all() never alters existing tables,
# so each one is added here, only if it is missing. Safe to run on every start.
COLUMN_MIGRATIONS = [
    ("event_suggestions", "warnings", "TEXT NOT NULL DEFAULT ''"),                    # 1.4.0
    ("event_suggestions", "end_date", "VARCHAR(10) NOT NULL DEFAULT ''"),             # 1.5.0
    ("event_suggestions", "url", "VARCHAR(1024) NOT NULL DEFAULT ''"),
    ("tasks", "category", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("tasks", "needs_reply", "BOOLEAN NOT NULL DEFAULT {false}"),
    ("tasks", "summary", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "is_bulk", "BOOLEAN NOT NULL DEFAULT {false}"),
    ("tasks", "is_forward", "BOOLEAN NOT NULL DEFAULT {false}"),
    ("tasks", "original_from", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("tasks", "original_subject", "VARCHAR(1024) NOT NULL DEFAULT ''"),
    ("tasks", "original_date", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("tasks", "related_json", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "action_items_json", "TEXT NOT NULL DEFAULT ''"),
]


def migrate() -> None:
    for table, column, ddl in COLUMN_MIGRATIONS:
        def present() -> bool:
            insp = inspect(engine)
            return table in insp.get_table_names() and column in {c["name"] for c in insp.get_columns(table)}

        if present() or table not in inspect(engine).get_table_names():
            continue
        try:
            with engine.begin() as conn:
                false = "FALSE" if engine.dialect.name == "postgresql" else "0"
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl.format(false=false)}"))
            log.info("Migration: added column %s.%s", table, column)
        except Exception:
            if not present():   # the web app and the worker may start at the same time
                raise


def init_db() -> None:
    Base.metadata.create_all(engine)
    migrate()
