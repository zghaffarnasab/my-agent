"""Write validated items to Postgres as draft records, with versioned dates and field evidence.

Rules (prompt section 5):
- New records land as `draft`. Nothing is ever published here; a human does that.
- A published record keeps its field values; new dates/evidence are added and a review note is set.
- Dates are versioned: a changed date from the same page supersedes the old row. If an official
  row exists and the new value comes from a lower tier, both stay current so `date_conflicts`
  shows them for review.
"""
from pipeline.sources import org_id

FUND_FIELDS = ("name", "strand", "organisation_id", "stages", "forms", "genres", "amount_min", "amount_max",
               "amount_currency", "amount_status", "amount_note", "deadline_mode", "residency_rule",
               "nationality_rule", "other_eligibility", "uk_eligible", "uk_not_eligible_reason", "is_accepting",
               "apply_url", "summary")
EVENT_FIELDS = ("name", "edition_year", "organisation_id", "event_type", "format", "city", "fee_min", "fee_max",
                "fee_currency", "fee_note", "genres", "submit_platform", "submit_url", "uk_eligible",
                "eligibility_note", "summary")
SOURCE_FIELDS = ("source_url", "source_id", "source_tier", "content_hash", "confidence")


def known_records(conn, source_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT 'fund' AS kind, slug::text, name FROM funds WHERE source_id = %s
           UNION ALL SELECT 'event', slug::text, name FROM events WHERE source_id = %s ORDER BY 2""",
        (source_id, source_id),
    ).fetchall()
    return [dict(r) for r in rows]


def _find_existing(conn, table: str, item: dict) -> dict | None:
    row = conn.execute(f"SELECT * FROM {table} WHERE slug = %s", (item["slug"],)).fetchone()
    if row:
        return row
    if table == "funds":
        row = conn.execute("SELECT * FROM funds WHERE name = %s AND strand IS NOT DISTINCT FROM %s",
                           (item["name"], item["strand"])).fetchone()
    else:
        row = conn.execute("SELECT * FROM events WHERE name = %s AND edition_year IS NOT DISTINCT FROM %s",
                           (item["name"], item["edition_year"])).fetchone()
    if row:
        return row
    # Fuzzy: same organisation and a very similar name (pg_trgm).
    if item.get("organisation_id"):
        extra = "AND strand IS NOT DISTINCT FROM %s" if table == "funds" else \
                "AND edition_year IS NOT DISTINCT FROM %s"
        key = item["strand"] if table == "funds" else item["edition_year"]
        return conn.execute(
            f"""SELECT * FROM {table} WHERE organisation_id = %s {extra} AND similarity(name, %s) >= 0.7
                ORDER BY similarity(name, %s) DESC LIMIT 1""",
            (item["organisation_id"], key, item["name"], item["name"]),
        ).fetchone()
    return None


def _upsert_record(conn, table: str, fields: tuple, item: dict, src: dict) -> tuple[int, str]:
    values = {f: item.get(f) for f in fields}
    values.update({"source_url": src["url"], "source_id": src["source_id"], "source_tier": src["tier"],
                   "content_hash": src["content_hash"], "confidence": item["confidence"]})
    existing = _find_existing(conn, table, item)
    if existing is None:
        cols = ["slug", *values]
        row = conn.execute(
            f"""INSERT INTO {table} ({', '.join(cols)}, last_verified_at, status)
                VALUES ({', '.join(['%s'] * len(cols))}, now(), 'draft') RETURNING id""",
            [item["slug"], *values.values()],
        ).fetchone()
        return row["id"], "created"
    if existing["status"] == "published":
        conn.execute(
            f"""UPDATE {table} SET last_verified_at = now(), content_hash = %s,
                  review_note = 'page changed: check new dates/evidence before the next sync'
                WHERE id = %s""",
            (src["content_hash"], existing["id"]),
        )
        return existing["id"], "flagged"
    sets = ", ".join(f"{c} = %s" for c in values)
    conn.execute(f"UPDATE {table} SET {sets}, last_verified_at = now() WHERE id = %s",
                 [*values.values(), existing["id"]])
    return existing["id"], "updated"


def _same_date(row: dict, d: dict) -> bool:
    return (row["status"] == d["status"] and row["date_value"] == d["date_value"]
            and (row["time_value"].strftime("%H:%M") if row["time_value"] else None) == d["time_value"]
            and row["approx_text"] == d["approx_text"])


def _store_date(conn, col: str, record_id: int, d: dict, src: dict) -> str:
    current = conn.execute(
        f"""SELECT * FROM record_dates WHERE {col} = %s AND kind = %s AND coalesce(label, '') = %s
              AND superseded_at IS NULL""",
        (record_id, d["kind"], d["label"] or ""),
    ).fetchall()
    for row in current:
        if _same_date(row, d):
            conn.execute("UPDATE record_dates SET last_verified_at = now() WHERE id = %s", (row["id"],))
            return "unchanged"
    new_id = conn.execute(
        f"""INSERT INTO record_dates ({col}, kind, label, status, date_value, time_value, tz, approx_text,
              approx_from, approx_to, source_url, source_tier, source_quote, snapshot_id, extraction_run_id,
              last_verified_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) RETURNING id""",
        (record_id, d["kind"], d["label"], d["status"], d["date_value"], d["time_value"], d["tz"],
         d["approx_text"], d["approx_from"], d["approx_to"], src["url"], src["tier"], d["source_quote"],
         src["snapshot_id"], src["run_id"]),
    ).fetchone()["id"]
    for row in current:
        same_page = row["source_url"] == src["url"]
        outranks_old = src["tier"] == "official" or row["source_tier"] != "official"
        if same_page or outranks_old:
            conn.execute("UPDATE record_dates SET superseded_at = now(), superseded_by = %s WHERE id = %s",
                         (new_id, row["id"]))
        # else: official old row vs. lower-tier new row -> both stay current (date_conflicts).
    return "changed" if current else "new"


def _store_evidence(conn, kind: str, record_id: int, ev: dict, confidence: float, src: dict) -> None:
    current = conn.execute(
        """SELECT id, value_text, source_url FROM field_evidence
           WHERE record_kind = %s AND record_id = %s AND field_name = %s AND superseded_at IS NULL""",
        (kind, record_id, ev["field"]),
    ).fetchall()
    if any(r["value_text"] == ev["value"] and r["source_url"] == src["url"] for r in current):
        return
    for r in current:
        if r["source_url"] == src["url"]:
            conn.execute("UPDATE field_evidence SET superseded_at = now() WHERE id = %s", (r["id"],))
    conn.execute(
        """INSERT INTO field_evidence (record_kind, record_id, field_name, value_text, source_quote, source_url,
             source_tier, snapshot_id, extraction_run_id, confidence)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (kind, record_id, ev["field"], ev["value"], ev["source_quote"], src["url"], src["tier"],
         src["snapshot_id"], src["run_id"], confidence),
    )


def store_items(conn, items: list[dict], src: dict) -> dict:
    """src: url, source_id, tier, content_hash, snapshot_id, run_id. Caller commits."""
    summary = {"created": 0, "updated": 0, "flagged": 0, "dates_new": 0, "dates_changed": 0}
    for item in items:
        item = dict(item, organisation_id=org_id(conn, item.get("organisation") or src.get("organisation")))
        if item["kind"] == "fund":
            table, fields, col = "funds", FUND_FIELDS, "fund_id"
        else:
            item["eligibility_note"] = item.get("uk_not_eligible_reason")
            table, fields, col = "events", EVENT_FIELDS, "event_id"
        record_id, outcome = _upsert_record(conn, table, fields, item, src)
        summary[outcome] += 1
        for d in item["dates"]:
            result = _store_date(conn, col, record_id, d, src)
            if result != "unchanged":
                summary[f"dates_{result}"] += 1
        for ev in item["evidence"]:
            _store_evidence(conn, item["kind"], record_id, ev, item["confidence"], src)
        for q in item.get("qualifying") or []:
            exists = conn.execute(
                """SELECT 1 FROM event_qualifications WHERE event_id = %s AND body = %s
                     AND category IS NOT DISTINCT FROM %s AND list_period IS NULL""",
                (record_id, q["body"], q["category"]),
            ).fetchone()
            if not exists:
                conn.execute(
                    """INSERT INTO event_qualifications (event_id, body, category, source_url, source_quote,
                         last_verified_at) VALUES (%s, %s, %s, %s, %s, now())""",
                    (record_id, q["body"], q["category"], src["url"], q["source_quote"]),
                )
    return summary
