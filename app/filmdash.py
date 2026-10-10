"""Review the filmmaker-dashboard drafts that the pipeline (pipeline/) stores in its own Postgres.

Read-only except for the review status. The app never imports the pipeline package: it talks to the
same tables with plain SQL. Nothing here publishes to the website; "published" only marks a record
as approved for the later Wix sync.
"""
import psycopg
from psycopg.rows import dict_row

from app import config

TABLES = {"fund": "funds", "event": "events"}
STATUSES = ("draft", "published", "rejected")
DATE_STATUSES = ("confirmed", "expected", "unverified", "conflict", "closed")
UK_ELIGIBLE = ("yes", "no", "partial", "unknown")

# (field, translation key) shown on the detail page, in this order.
FUND_FIELDS = [
    ("amount", "film.field.amount"), ("amount_note", "film.field.amount_note"),
    ("stages", "film.field.stages"), ("forms", "film.field.forms"), ("genres", "film.field.genres"),
    ("deadline_mode", "film.field.deadline_mode"), ("is_accepting", "film.field.is_accepting"),
    ("residency_rule", "film.field.residency_rule"), ("nationality_rule", "film.field.nationality_rule"),
    ("other_eligibility", "film.field.other_eligibility"), ("apply_url", "film.field.apply_url"),
]
EVENT_FIELDS = [
    ("event_type", "film.field.event_type"), ("edition_year", "film.field.edition_year"),
    ("format", "film.field.format"), ("city", "film.field.city"), ("fee", "film.field.fee"),
    ("fee_note", "film.field.fee_note"), ("genres", "film.field.genres"),
    ("submit_platform", "film.field.submit_platform"), ("submit_url", "film.field.submit_url"),
]


class Unavailable(Exception):
    """The pipeline database is not configured or cannot be reached."""


def enabled() -> bool:
    return bool(config.FILMDASH_DATABASE_URL)


def _connect():
    if not enabled():
        raise Unavailable("not configured")
    try:
        return psycopg.connect(config.FILMDASH_DATABASE_URL, row_factory=dict_row, connect_timeout=5)
    except psycopg.OperationalError as exc:
        raise Unavailable(str(exc)) from exc


def _money(lo, hi, currency) -> str:
    if lo is None and hi is None:
        return ""
    fmt = lambda v: f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
    cur = f" {currency}" if currency else ""
    if lo is not None and hi is not None and lo != hi:
        return f"{fmt(lo)}–{fmt(hi)}{cur}"
    return f"{fmt(hi if hi is not None else lo)}{cur}"


_LIST_SQL = """
SELECT 'fund' AS kind, f.id, f.name, f.strand AS sub, o.name::text AS org, f.uk_eligible::text AS uk_eligible,
       f.status::text AS status, f.source_url::text AS source_url, f.updated_at,
       (SELECT min(d.date_value) FROM current_dates d WHERE d.fund_id = f.id AND d.date_value >= current_date)
         AS next_date
FROM funds f LEFT JOIN organisations o ON o.id = f.organisation_id WHERE f.status = %(status)s
UNION ALL
SELECT 'event', e.id, e.name, e.edition_year::text, o.name::text, e.uk_eligible::text,
       e.status::text, e.source_url::text, e.updated_at,
       (SELECT min(d.date_value) FROM current_dates d WHERE d.event_id = e.id AND d.date_value >= current_date)
FROM events e LEFT JOIN organisations o ON o.id = e.organisation_id WHERE e.status = %(status)s
ORDER BY next_date NULLS LAST, name
"""


def overview(status: str) -> tuple[list[dict], dict]:
    """Records with this review status (soonest upcoming date first) and the count per status."""
    with _connect() as conn:
        rows = conn.execute(_LIST_SQL, {"status": status}).fetchall()
        counts = {s: 0 for s in STATUSES}
        for r in conn.execute("""SELECT status::text AS s, count(*) AS n FROM funds GROUP BY 1
                                 UNION ALL SELECT status::text, count(*) FROM events GROUP BY 1"""):
            counts[r["s"]] += r["n"]
    return rows, counts


def get(kind: str, record_id: int) -> dict | None:
    table = TABLES[kind]
    col = "fund_id" if kind == "fund" else "event_id"
    with _connect() as conn:
        rec = conn.execute(
            f"""SELECT r.*, r.status::text AS status, r.uk_eligible::text AS uk_eligible,
                       r.source_tier::text AS source_tier, r.source_url::text AS source_url, o.name::text AS org
                       {", r.stages::text[] AS stages_list" if kind == "fund" else ""}
                FROM {table} r LEFT JOIN organisations o ON o.id = r.organisation_id WHERE r.id = %s""",
            (record_id,),
        ).fetchone()
        if rec is None:
            return None
        rec = dict(rec)
        if kind == "fund":
            rec["stages"] = rec.pop("stages_list")
            rec["amount"] = _money(rec["amount_min"], rec["amount_max"], rec["amount_currency"])
            if rec["amount"]:
                rec["amount"] += f" ({rec['amount_status']})"
        else:
            rec["fee"] = _money(rec["fee_min"], rec["fee_max"], rec["fee_currency"])
        rec["dates"] = conn.execute(
            f"""SELECT kind::text AS kind, label, status::text AS status, date_value, time_value, tz, approx_text,
                       source_quote, source_url, source_tier::text AS source_tier
                FROM current_dates WHERE {col} = %s
                ORDER BY coalesce(date_value, approx_from) NULLS LAST, kind""",
            (record_id,),
        ).fetchall()
        rec["evidence"] = conn.execute(
            """SELECT field_name, value_text, source_quote, source_url FROM field_evidence
               WHERE record_kind = %s AND record_id = %s AND superseded_at IS NULL ORDER BY field_name, id""",
            (kind, record_id),
        ).fetchall()
        rec["qualifications"] = conn.execute(
            "SELECT body, category, source_quote FROM event_qualifications WHERE event_id = %s ORDER BY body",
            (record_id,),
        ).fetchall() if kind == "event" else []
        run = conn.execute(
            """SELECT er.raw_output->>'notes' AS notes, jsonb_array_length(coalesce(er.rejected_items, '[]')) AS rejected
               FROM extraction_runs er JOIN snapshots s ON s.id = er.snapshot_id
               WHERE s.source_id = %s AND s.content_hash = %s AND er.ok ORDER BY er.id DESC LIMIT 1""",
            (rec["source_id"], rec["content_hash"]),
        ).fetchone()
        rec["notes"], rec["rejected_count"] = (run["notes"], run["rejected"]) if run else (None, 0)
    fields = FUND_FIELDS if kind == "fund" else EVENT_FIELDS
    rec["fields"] = [(key, _show(rec.get(name))) for name, key in fields if _show(rec.get(name))]
    return rec


def _show(value) -> str:
    if value is None or value == "" or value == [] or value == "unknown":
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def set_status(kind: str, record_id: int, status: str, note: str = "") -> bool:
    if status not in STATUSES:
        raise ValueError(status)
    with _connect() as conn:
        cur = conn.execute(
            f"""UPDATE {TABLES[kind]} SET status = %s, reviewed_by = 'dashboard', reviewed_at = now(),
                  review_note = %s WHERE id = %s""",
            (status, note.strip()[:1000] or None, record_id),
        )
        conn.commit()
        return cur.rowcount == 1
