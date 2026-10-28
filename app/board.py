"""Task board (/board): simple to-dos in three columns (to do, in progress, done), each owned by one person.

The people are names typed on the Settings page (settings key "board_people", comma-separated).
Cards live in the app's own database and have nothing to do with emails.
"""
from datetime import date

from sqlalchemy import delete as sql_delete, func, select

from app import settings
from app.db import BoardCard, BoardImage, BoardStatus, SessionLocal, utcnow

MAX_PEOPLE = 6
MAX_TITLE = 300
MAX_NOTES = 4000
PERSON_COLORS = 6     # CSS classes .who-0 ... .who-5, one per person in Settings order
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 10       # per card

# Only real pictures are kept, recognised by their first bytes (never by the name or the browser's claim).
_IMAGE_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def clean_people(raw: str) -> str:
    """What the Settings page stores: the names, without blanks or duplicates, joined with ", "."""
    names: list[str] = []
    for name in (raw or "").replace("\u060c", ",").split(","):   # the Persian comma counts too
        name = " ".join(name.split())[:64]
        if name and name.casefold() not in {p.casefold() for p in names}:
            names.append(name)
    return ", ".join(names[:MAX_PEOPLE])


def people() -> list[str]:
    """The board people, in Settings order."""
    return [n for n in clean_people(settings.get("board_people")).split(", ") if n]


def color_of(name: str) -> int:
    """A stable color index for a person: their place in the Settings list (unknown names share the last color)."""
    names = people()
    return names.index(name) % PERSON_COLORS if name in names else PERSON_COLORS - 1


def clean_due(value: str) -> str:
    value = (value or "").strip()
    try:
        return date.fromisoformat(value).isoformat() if value else ""
    except ValueError:
        return ""


def clean_card(title: str, notes: str, assignee: str, due: str, priority: str = "low") -> dict | None:
    """Validated card fields, or None when the title is empty or the person is not on the board."""
    title = " ".join((title or "").split())[:MAX_TITLE]
    if not title or assignee not in people():
        return None
    return {"title": title, "notes": (notes or "").strip()[:MAX_NOTES], "assignee": assignee, "due": clean_due(due),
            "priority": priority if priority in BoardStatus.PRIORITIES else "low"}


def image_type(data: bytes) -> str:
    """The picture's media type from its first bytes, or "" when it is not a PNG, JPEG, GIF or WebP (or is too big)."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        return ""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return next((kind for magic, kind in _IMAGE_MAGIC if data.startswith(magic)), "")


def add_images(card_id: int, blobs: list[bytes]) -> int:
    """Keep the pictures among `blobs` (up to MAX_IMAGES per card). Returns how many were skipped."""
    skipped = 0
    with SessionLocal() as db:
        if db.get(BoardCard, card_id) is None:
            return len(blobs)
        room = MAX_IMAGES - db.scalar(select(func.count()).where(BoardImage.card_id == card_id))
        for data in blobs:
            kind = image_type(data)
            if not kind or room <= 0:
                skipped += 1
                continue
            db.add(BoardImage(card_id=card_id, content_type=kind, data=data))
            room -= 1
        db.commit()
    return skipped


def remove_images(card_id: int, image_ids: list[int]) -> None:
    if image_ids:
        with SessionLocal() as db:
            db.execute(sql_delete(BoardImage).where(BoardImage.card_id == card_id, BoardImage.id.in_(image_ids)))
            db.commit()


def get_image(image_id: int) -> BoardImage | None:
    with SessionLocal() as db:
        return db.get(BoardImage, image_id)


def image_ids() -> dict[int, list[int]]:
    """The picture ids of every card, oldest first (the pictures themselves are fetched one by one)."""
    with SessionLocal() as db:
        rows = db.execute(select(BoardImage.card_id, BoardImage.id).order_by(BoardImage.id)).all()
    out: dict[int, list[int]] = {}
    for card_id, image_id in rows:
        out.setdefault(card_id, []).append(image_id)
    return out


def columns(who: str = "") -> dict[str, list[BoardCard]]:
    """The cards of each column, in board order. `who` limits the board to one person."""
    with SessionLocal() as db:
        q = select(BoardCard).order_by(BoardCard.position, BoardCard.id)
        if who:
            q = q.where(BoardCard.assignee == who)
        cards = db.scalars(q).all()
    out: dict[str, list[BoardCard]] = {s: [] for s in BoardStatus.ALL}
    for card in cards:
        out.get(card.status, out[BoardStatus.TODO]).append(card)
    return out


def open_counts() -> dict[str, int]:
    """Unfinished cards per person (for the filter buttons)."""
    with SessionLocal() as db:
        rows = db.execute(select(BoardCard.assignee, func.count()).where(BoardCard.status != BoardStatus.DONE)
                          .group_by(BoardCard.assignee)).all()
    return {name: n for name, n in rows}


def _end_position(db, status: str) -> int:
    top = db.scalar(select(func.max(BoardCard.position)).where(BoardCard.status == status))
    return (top or 0) + 1


def create(fields: dict, status: str = BoardStatus.TODO) -> int:
    status = status if status in BoardStatus.ALL else BoardStatus.TODO
    with SessionLocal() as db:
        card = BoardCard(**fields, status=status, position=_end_position(db, status),
                         done_at=utcnow() if status == BoardStatus.DONE else None)
        db.add(card)
        db.commit()
        return card.id


def update(card_id: int, fields: dict, status: str = "") -> bool:
    """Save edited fields; a new `status` moves the card to the end of that column."""
    with SessionLocal() as db:
        card = db.get(BoardCard, card_id)
        if card is None:
            return False
        for key, value in fields.items():
            setattr(card, key, value)
        new_column = status in BoardStatus.ALL and status != card.status
        db.commit()
    return move(card_id, status) if new_column else True


def move(card_id: int, status: str, before_id: int | None = None) -> bool:
    """Put a card in a column: just above card `before_id`, or at the end of the column."""
    if status not in BoardStatus.ALL:
        return False
    with SessionLocal() as db:
        card = db.get(BoardCard, card_id)
        if card is None:
            return False
        if card.status != status:
            card.done_at = utcnow() if status == BoardStatus.DONE else None
        card.status = status
        others = [c for c in db.scalars(select(BoardCard).where(BoardCard.status == status, BoardCard.id != card_id)
                                        .order_by(BoardCard.position, BoardCard.id))]
        at = next((i for i, c in enumerate(others) if c.id == before_id), len(others))
        others.insert(at, card)
        for i, c in enumerate(others, start=1):
            c.position = i
        db.commit()
        return True


def step(card_id: int, direction: int) -> bool:
    """Move a card one column to the right (+1) or left (-1), to the end of that column."""
    with SessionLocal() as db:
        card = db.get(BoardCard, card_id)
        if card is None:
            return False
        i = BoardStatus.ALL.index(card.status) if card.status in BoardStatus.ALL else 0
    j = min(max(i + direction, 0), len(BoardStatus.ALL) - 1)
    return move(card_id, BoardStatus.ALL[j])


def delete(card_id: int) -> bool:
    with SessionLocal() as db:
        card = db.get(BoardCard, card_id)
        if card is None:
            return False
        db.execute(sql_delete(BoardImage).where(BoardImage.card_id == card_id))   # SQLite does not cascade by itself
        db.delete(card)
        db.commit()
        return True
