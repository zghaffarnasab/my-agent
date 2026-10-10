"""One-way sync of PUBLISHED funds and events to two Wix CMS collections (Postgres stays the source of truth).

- Only records with status 'published' (approved on the /film review page) are sent. Drafts never leave Postgres.
- A record that is no longer published (rejected or back to draft) is removed from Wix.
- Each Wix item id is derived from the record id, so re-running is safe and never duplicates items.
- An item is re-sent only when its payload changed (`wix_sync_hash`). Payloads include `displayStatus`
  ('published' or 'expired'), so a daily run also marks items whose deadlines have passed.

Auth: a Wix API key (WIX_API_KEY) with CMS permissions, plus the site id (WIX_SITE_ID); see pipeline/README.md.
"""
import hashlib
import json
import logging
import uuid
from datetime import date

import httpx

from pipeline import config

log = logging.getLogger(__name__)

API = "https://www.wixapis.com/wix-data/v2"
BATCH = 100
_NAMESPACE = uuid.UUID("6f1c3a52-6d0e-4d1b-9a43-6a1f5d0b7e21")

_COMMON_FIELDS = [
    ("title", "Name", "TEXT"),
    ("slug", "Slug", "TEXT"),
    ("organisation", "Organisation", "TEXT"),
    ("summary", "Summary", "TEXT"),
    ("ukEligible", "UK eligible", "TEXT"),
    ("eligibility", "Eligibility", "TEXT"),
    ("genres", "Genres", "ARRAY_STRING"),
    ("nextDeadline", "Next deadline", "DATE"),
    ("nextDeadlineStatus", "Next deadline status", "TEXT"),
    ("upcomingDates", "Upcoming dates", "TEXT"),
    ("sourceUrl", "Official page", "URL"),
    ("lastVerified", "Last verified", "DATE"),
    ("displayStatus", "Status", "TEXT"),
]
FUND_FIELDS = _COMMON_FIELDS + [
    ("strand", "Strand", "TEXT"),
    ("stages", "Stages", "ARRAY_STRING"),
    ("forms", "Forms", "ARRAY_STRING"),
    ("amount", "Amount", "TEXT"),
    ("amountMin", "Amount min", "NUMBER"),
    ("amountMax", "Amount max", "NUMBER"),
    ("currency", "Currency", "TEXT"),
    ("deadlineMode", "Deadline mode", "TEXT"),
    ("isAccepting", "Accepting applications", "BOOLEAN"),
    ("applyUrl", "Apply link", "URL"),
]
EVENT_FIELDS = _COMMON_FIELDS + [
    ("edition", "Edition", "TEXT"),
    ("eventType", "Type", "TEXT"),
    ("format", "Format", "TEXT"),
    ("city", "City", "TEXT"),
    ("country", "Country", "TEXT"),
    ("startDate", "Start date", "DATE"),
    ("endDate", "End date", "DATE"),
    ("fee", "Fee", "TEXT"),
    ("submitPlatform", "Submit via", "TEXT"),
    ("submitUrl", "Submit link", "URL"),
]

KINDS = {
    "fund": {"table": "funds", "view": "funds_v", "date_col": "fund_id", "fields": FUND_FIELDS,
             "collection": lambda: config.WIX_FUNDS_COLLECTION, "display": "Film Funds"},
    "event": {"table": "events", "view": "events_v", "date_col": "event_id", "fields": EVENT_FIELDS,
              "collection": lambda: config.WIX_EVENTS_COLLECTION, "display": "Film Events"},
}


class WixError(RuntimeError):
    pass


def item_id(kind: str, record_id: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"filmdash:{kind}:{record_id}"))


def make_client() -> httpx.Client:
    key = config.require("WIX_API_KEY", config.WIX_API_KEY)
    site = config.require("WIX_SITE_ID", config.WIX_SITE_ID)
    return httpx.Client(base_url=API, timeout=30,
                        headers={"Authorization": key, "wix-site-id": site, "Content-Type": "application/json"})


def _call(client: httpx.Client, method: str, path: str, body: dict | None = None) -> dict:
    resp = client.request(method, path, json=body)
    if resp.status_code >= 400:
        raise WixError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}


# --- collections ---------------------------------------------------------------------------------

def ensure_collections(client: httpx.Client) -> list[str]:
    """Create the two collections if missing, and add any field they lack. Never deletes anything."""
    done = []
    for kind, spec in KINDS.items():
        cid = spec["collection"]()
        resp = client.get(f"/collections/{cid}")
        if resp.status_code == 404:
            _call(client, "POST", "/collections", {"collection": {
                "id": cid, "displayName": spec["display"],
                "fields": [{"key": k, "displayName": n, "type": t} for k, n, t in spec["fields"]],
                # Visitors can read; only the site owner (and this API key) can write.
                "permissions": {"insert": "ADMIN", "update": "ADMIN", "remove": "ADMIN", "read": "ANYONE"},
            }})
            done.append(f"created {cid}")
            continue
        if resp.status_code >= 400:
            raise WixError(f"GET /collections/{cid} -> HTTP {resp.status_code}: {resp.text[:500]}")
        have = {f["key"] for f in resp.json().get("collection", {}).get("fields", [])}
        for k, n, t in spec["fields"]:
            if k not in have:
                _call(client, "POST", "/collections/create-field",
                      {"dataCollectionId": cid, "field": {"key": k, "displayName": n, "type": t}})
                done.append(f"added {cid}.{k}")
    return done


# --- payloads ------------------------------------------------------------------------------------

def _money(lo, hi, currency) -> str | None:
    if lo is None and hi is None:
        return None
    fmt = lambda v: f"{v:,.0f}"  # noqa: E731
    cur = f"{currency} " if currency else ""
    if lo is not None and hi is not None and lo != hi:
        return f"{cur}{fmt(lo)} - {fmt(hi)}"
    return f"{cur}{fmt(hi if hi is not None else lo)}"


def _num(v):
    return float(v) if v is not None else None


def _iso(v) -> str | None:
    """date or datetime -> 'YYYY-MM-DD'."""
    if v is None:
        return None
    if hasattr(v, "hour"):
        v = v.date()
    return v.isoformat()


def _dates_text(dates: list[dict]) -> str | None:
    """Upcoming confirmed dates and 'not announced yet' estimates, one per line, soonest first."""
    lines = []
    for d in dates:
        what = d["label"] or d["kind"].replace("_", " ")
        if d["label"] and d["kind"] not in d["label"].lower():
            what = f"{d['label']} ({d['kind'].replace('_', ' ')})"
        if d["date_value"]:
            when = d["date_value"].strftime("%-d %b %Y")
            if d["time_value"]:
                when += f" {d['time_value'].strftime('%H:%M')}"
            lines.append(f"{when}: {what}" + ("" if d["status"] == "confirmed" else f" [{d['status']}]"))
        else:
            lines.append(f"{d['approx_text'] or 'Date not announced'}: {what} [expected]")
    return "\n".join(lines) or None


def _dates(conn, col: str, record_id: int) -> list[dict]:
    return conn.execute(
        f"""SELECT kind::text AS kind, label, status::text AS status, date_value, time_value, approx_text
            FROM current_dates WHERE {col} = %s
              AND (date_value >= current_date
                   OR (status = 'expected' AND coalesce(approx_to, approx_from, current_date) >= current_date))
            ORDER BY coalesce(date_value, approx_from) NULLS LAST, kind""",
        (record_id,),
    ).fetchall()


def build_payload(conn, kind: str, rec: dict) -> dict:
    spec = KINDS[kind]
    dates = _dates(conn, spec["date_col"], rec["id"])
    data = {
        "title": rec["name"], "slug": rec["slug"], "organisation": rec["org"], "summary": rec["summary"],
        "ukEligible": rec["uk_eligible"], "genres": list(rec["genres"] or []),
        "nextDeadline": _iso(rec["next_deadline"]), "nextDeadlineStatus": rec["next_deadline_status"],
        "upcomingDates": _dates_text(dates), "sourceUrl": rec["source_url"],
        "lastVerified": _iso(rec["last_verified_at"]), "displayStatus": rec["display_status"],
    }
    if kind == "fund":
        data["eligibility"] = "\n".join(filter(None, [rec["residency_rule"], rec["nationality_rule"],
                                                       rec["other_eligibility"], rec["uk_not_eligible_reason"]])) or None
        data.update({
            "strand": rec["strand"], "stages": list(rec["stages"] or []), "forms": list(rec["forms"] or []),
            "amount": _money(rec["amount_min"], rec["amount_max"], rec["amount_currency"]),
            "amountMin": _num(rec["amount_min"]), "amountMax": _num(rec["amount_max"]),
            "currency": rec["amount_currency"], "deadlineMode": rec["deadline_mode"],
            "isAccepting": rec["is_accepting"], "applyUrl": rec["apply_url"],
        })
    else:
        days = {d["kind"]: d["date_value"] for d in conn.execute(
            """SELECT kind::text AS kind, min(date_value) AS date_value FROM current_dates
               WHERE event_id = %s AND kind IN ('event_start', 'event_end') GROUP BY kind""", (rec["id"],))}
        data.update({
            "eligibility": rec["eligibility_note"], "edition": rec["edition"], "eventType": rec["event_type"],
            "format": rec["format"], "city": rec["city"], "country": rec["country"],
            "startDate": _iso(days.get("event_start")), "endDate": _iso(days.get("event_end")),
            "fee": _money(rec["fee_min"], rec["fee_max"], rec["fee_currency"]),
            "submitPlatform": rec["submit_platform"], "submitUrl": rec["submit_url"],
        })
    # Wix leaves out fields that are not sent; drop empty values so the CMS shows them as empty.
    return {k: v for k, v in data.items() if v not in (None, "", [])}


def payload_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _published(conn, kind: str) -> list[dict]:
    spec = KINDS[kind]
    extra = ", r.stages::text[] AS stages" if kind == "fund" else ""
    return conn.execute(
        f"""SELECT r.*, r.slug::text AS slug, r.source_url::text AS source_url, r.uk_eligible::text AS uk_eligible,
                   r.next_deadline_status::text AS next_deadline_status, o.name::text AS org {extra}
                   {", r.deadline_mode::text AS deadline_mode" if kind == "fund" else
                    ", r.event_type::text AS event_type, r.format::text AS format,"
                    " r.submit_platform::text AS submit_platform"}
            FROM {spec['view']} r LEFT JOIN organisations o ON o.id = r.organisation_id
            WHERE r.status = 'published' ORDER BY r.id"""
    ).fetchall()


# --- sync ----------------------------------------------------------------------------------------

def plan(conn) -> dict:
    """What a sync would do, without calling Wix: {kind: {"save": [(id, item_id, data, hash)], "remove": [...]}}."""
    out = {}
    for kind, spec in KINDS.items():
        save = []
        for rec in _published(conn, kind):
            data = build_payload(conn, kind, rec)
            h = payload_hash(data)
            if h != rec["wix_sync_hash"] or not rec["wix_item_id"]:
                save.append((rec["id"], rec["wix_item_id"] or item_id(kind, rec["id"]), data, h))
        remove = conn.execute(
            f"SELECT id, wix_item_id FROM {spec['table']} WHERE wix_item_id IS NOT NULL AND status <> 'published'"
        ).fetchall()
        out[kind] = {"save": save, "remove": [(r["id"], r["wix_item_id"]) for r in remove]}
    return out


def sync(conn, client: httpx.Client | None = None, *, dry_run: bool = False) -> dict:
    """Push changes to Wix. Returns counts per kind; per-item failures are listed, not raised."""
    todo = plan(conn)
    if dry_run:
        return {kind: {"would_save": [d["title"] for _, _, d, _ in t["save"]],
                       "would_remove": [rid for rid, _ in t["remove"]]} for kind, t in todo.items()}
    own_client = client is None
    client = client or make_client()
    try:
        summary = {"collections": ensure_collections(client)}
        for kind, t in todo.items():
            spec = KINDS[kind]
            cid = spec["collection"]()
            saved, failed = 0, []
            for i in range(0, len(t["save"]), BATCH):
                chunk = t["save"][i:i + BATCH]
                resp = _call(client, "POST", "/bulk/items/save", {
                    "dataCollectionId": cid, "dataItems": [{"id": wid, "data": d} for _, wid, d, _ in chunk]})
                ok = _successes(resp, len(chunk))
                for (rid, wid, d, h), good in zip(chunk, ok):
                    if good:
                        conn.execute(f"""UPDATE {spec['table']} SET wix_item_id = %s, wix_synced_at = now(),
                                         wix_sync_hash = %s WHERE id = %s""", (wid, h, rid))
                        saved += 1
                    else:
                        failed.append(d["title"])
                conn.commit()
            removed = 0
            for i in range(0, len(t["remove"]), BATCH):
                chunk = t["remove"][i:i + BATCH]
                resp = _call(client, "POST", "/bulk/items/remove",
                             {"dataCollectionId": cid, "dataItemIds": [wid for _, wid in chunk]})
                for (rid, _), good in zip(chunk, _successes(resp, len(chunk), missing_ok=True)):
                    if good:
                        conn.execute(f"""UPDATE {spec['table']} SET wix_item_id = NULL, wix_synced_at = now(),
                                         wix_sync_hash = NULL WHERE id = %s""", (rid,))
                        removed += 1
                conn.commit()
            summary[kind] = {"saved": saved, "removed": removed, "failed": failed}
        log.info("wix sync: %s", summary)
        return summary
    finally:
        if own_client:
            client.close()


def _successes(resp: dict, n: int, missing_ok: bool = False) -> list[bool]:
    """Per-item success flags from a bulk response, in request order."""
    flags = [False] * n
    for r in resp.get("results", []):
        meta = r.get("itemMetadata") or {}
        idx = meta.get("originalIndex")
        if idx is None or not 0 <= idx < n:
            continue
        err = (meta.get("error") or {}).get("code", "")
        flags[idx] = bool(meta.get("success")) or (missing_ok and "NOT_FOUND" in str(err).upper())
    return flags
