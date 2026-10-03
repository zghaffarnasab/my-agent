from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import DATABASE_URL

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
    SKIPPED = "skipped"      # newsletter / automated / own email; never shown as a task


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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleCredential(Base):
    """Single row (id=1) holding the OAuth token of the connected Gmail account."""
    __tablename__ = "google_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(512), default="")
    token_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)
