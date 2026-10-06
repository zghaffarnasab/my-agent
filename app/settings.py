"""Settings stored in the database (language, time zone), falling back to .env values."""
import time
from zoneinfo import ZoneInfo

from app import config, i18n
from app.db import Setting, SessionLocal

_TTL_SECONDS = 5
_cache: dict[str, tuple[float, str]] = {}


def get(key: str) -> str:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _TTL_SECONDS:
        return hit[1]
    with SessionLocal() as db:
        row = db.get(Setting, key)
        value = row.value if row else ""
    _cache[key] = (time.monotonic(), value)
    return value


def set(key: str, value: str) -> None:
    with SessionLocal() as db:
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
        db.commit()
    _cache.pop(key, None)


def get_language() -> str:
    """The app's configured language (also used for AI-written text)."""
    return i18n.normalize(get("language"), default=i18n.normalize(config.DEFAULT_LANGUAGE))


def get_timezone() -> str:
    value = get("timezone")
    if value:
        try:
            return ZoneInfo(value).key
        except Exception:
            pass
    return config.TIMEZONE


def is_valid_timezone(value: str) -> bool:
    try:
        ZoneInfo(value)
        return bool(value.strip())
    except Exception:
        return False
