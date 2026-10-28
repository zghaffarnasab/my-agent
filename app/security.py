"""Login protection: lockout after wrong passwords, server-side sign-out, safe headers and same-origin checks."""
import secrets
import threading
import time
from urllib.parse import urlsplit

from app import settings

MAX_FAILURES = 5              # wrong passwords from one address ...
FAILURE_WINDOW = 15 * 60      # ... within this many seconds ...
LOCKOUT_SECONDS = 15 * 60     # ... lock that address out for this long

EPOCH_KEY = "session_epoch"   # settings key; changing it signs out every browser

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}


def locked_for(ip: str) -> int:
    """Seconds this address must still wait before it may try a password again (0 = may try)."""
    with _lock:
        left = _locked_until.get(ip, 0) - time.monotonic()
        if left <= 0:
            _locked_until.pop(ip, None)
            return 0
        return int(left) + 1


def record_failure(ip: str) -> None:
    now = time.monotonic()
    with _lock:
        recent = [t for t in _failures.get(ip, []) if now - t < FAILURE_WINDOW]
        recent.append(now)
        if len(recent) >= MAX_FAILURES:
            _locked_until[ip] = now + LOCKOUT_SECONDS
            recent = []
        _failures[ip] = recent
        if len(_failures) > 10_000:  # never let the table grow without limit
            _failures.clear()


def record_success(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


def reset() -> None:
    with _lock:
        _failures.clear()
        _locked_until.clear()


def session_epoch() -> str:
    epoch = settings.get(EPOCH_KEY)
    if not epoch:
        epoch = secrets.token_urlsafe(12)
        settings.set(EPOCH_KEY, epoch)
    return epoch


def sign_out_everywhere() -> None:
    settings.set(EPOCH_KEY, secrets.token_urlsafe(12))


def same_origin(origin: str | None, host: str | None) -> bool:
    """A browser POST must come from our own pages. No Origin header (old browsers, curl) is allowed."""
    if not origin:
        return True
    return bool(host) and urlsplit(origin).netloc.lower() == host.lower()


def security_headers(https: bool) -> dict[str, str]:
    headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    if https:
        headers["Strict-Transport-Security"] = "max-age=31536000"
    return headers
