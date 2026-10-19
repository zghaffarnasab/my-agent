"""Visit statistics of the company website (/stats).

The website stores one anonymous row per page view in `site_visits` in the same Postgres as the
pipeline (no cookie, IP or user agent; `visitor` is a hash that changes every day, see the website's
migration V3__site_visits.sql). This module only reads that table.

A visitor is counted once per day: the same person on two days counts twice, because the website
cannot (by design) recognise anyone across days.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg

from app import filmdash, settings

PERIODS = (7, 30, 90)
DEVICES = ("mobile", "tablet", "desktop")
LANGS = ("en", "fa")
KNOWN_PATHS = {"/": "home", "/opportunities": "opportunities", "/confirm": "confirm", "/other": "other"}
TOP = 15


def enabled() -> bool:
    return filmdash.enabled()


def _connect():
    conn = filmdash._connect()
    try:
        conn.execute("SELECT 1 FROM site_visits LIMIT 0")
    except psycopg.errors.UndefinedTable as exc:
        conn.close()
        raise filmdash.Unavailable("no table") from exc
    return conn


# A visitor-day: the daily hash is only unique within one day, so it is paired with the local date.
_DAY = "(created_at AT TIME ZONE %(tz)s)::date"
_VISITOR_DAY = f"({_DAY}::text || visitor)"


def summary(days: int, today: date | None = None) -> dict:
    """Views and visitors of the last `days` days (today included), in the configured time zone."""
    days = days if days in PERIODS else PERIODS[1]
    tz = settings.get_timezone()
    today = today or datetime.now(ZoneInfo(tz)).date()
    first = today - timedelta(days=days - 1)
    params = {"tz": tz, "since": datetime(first.year, first.month, first.day, tzinfo=ZoneInfo(tz)), "top": TOP}
    where = "WHERE created_at >= %(since)s"
    with _connect() as conn:
        per_day = {r["day"]: r for r in conn.execute(
            f"SELECT {_DAY} AS day, count(*) AS views, count(DISTINCT visitor) AS visitors "
            f"FROM site_visits {where} GROUP BY 1", params)}
        pages = conn.execute(
            f"SELECT path, count(*) AS views, count(DISTINCT {_VISITOR_DAY}) AS visitors "
            f"FROM site_visits {where} GROUP BY path ORDER BY views DESC, path LIMIT %(top)s", params).fetchall()
        referrers = conn.execute(
            f"SELECT referrer, count(*) AS views FROM site_visits {where} AND referrer IS NOT NULL "
            f"GROUP BY referrer ORDER BY views DESC, referrer LIMIT %(top)s", params).fetchall()
        devices = {r["device"]: r["visitors"] for r in conn.execute(
            f"SELECT device, count(DISTINCT {_VISITOR_DAY}) AS visitors FROM site_visits {where} GROUP BY device",
            params)}
        langs = {r["lang"]: r["visitors"] for r in conn.execute(
            f"SELECT lang, count(DISTINCT {_VISITOR_DAY}) AS visitors FROM site_visits {where} GROUP BY lang",
            params)}

    daily = []
    for offset in range(days):
        day = first + timedelta(days=offset)
        row = per_day.get(day) or {}
        daily.append({"day": day, "views": row.get("views", 0), "visitors": row.get("visitors", 0)})
    peak = max((d["views"] for d in daily), default=0)
    for d in daily:
        d["pct"] = round(100 * d["views"] / peak) if peak else 0
    visitors = sum(d["visitors"] for d in daily)
    return {
        "days": days,
        "first": first,
        "today": daily[-1],
        "views": sum(d["views"] for d in daily),
        "visitors": visitors,
        "daily": daily,
        "pages": [dict(p, label=KNOWN_PATHS.get(p["path"])) for p in pages],
        "referrers": referrers,
        "devices": _shares(devices, DEVICES),
        "langs": _shares(langs, LANGS),
    }


def _shares(counts: dict, keys: tuple) -> list[dict]:
    total = sum(counts.values())
    return [{"key": k, "n": counts.get(k, 0), "pct": round(100 * counts.get(k, 0) / total) if total else 0}
            for k in keys]
