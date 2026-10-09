"""Glue: snapshot -> Claude -> validation -> Postgres, with an extraction_runs row for every call."""
import logging

from psycopg.types.json import Jsonb

from pipeline import config, extract, fetch, store, validate

log = logging.getLogger(__name__)


def pending_snapshots(conn) -> list[int]:
    """Latest snapshot of each active source that has no successful extraction yet."""
    rows = conn.execute(
        """SELECT DISTINCT ON (s.source_id) s.id, s.source_id
           FROM snapshots s JOIN sources src ON src.id = s.source_id AND src.is_active
           ORDER BY s.source_id, s.fetched_at DESC"""
    ).fetchall()
    out = []
    for r in rows:
        done = conn.execute(
            "SELECT 1 FROM extraction_runs WHERE snapshot_id = %s AND ok AND prompt_version = %s",
            (r["id"], config.PROMPT_VERSION),
        ).fetchone()
        if not done:
            out.append(r["id"])
    return out


def extract_snapshot(conn, client, snapshot_id: int) -> dict:
    snap = conn.execute(
        """SELECT sn.*, src.url, src.tier, o.name AS organisation
           FROM snapshots sn JOIN sources src ON src.id = sn.source_id
           LEFT JOIN organisations o ON o.id = src.organisation_id WHERE sn.id = %s""",
        (snapshot_id,),
    ).fetchone()
    model = config.EXTRACT_MODEL
    run_id = conn.execute(
        "INSERT INTO extraction_runs (snapshot_id, model, prompt_version) VALUES (%s, %s, %s) RETURNING id",
        (snapshot_id, model, config.PROMPT_VERSION),
    ).fetchone()["id"]
    conn.commit()   # the run row survives even if the call below fails

    try:
        message = extract.build_user_message(
            clean_text=snap["clean_text"], source_url=snap["url"], source_tier=snap["tier"],
            organisation=snap["organisation"], page_modified=snap["page_modified"],
            known_records=store.known_records(conn, snap["source_id"]),
        )
        output, usage = extract.call_claude(client, message, model)
        checked = validate.validate_extraction(output, snap["clean_text"], snap["tier"])
        src = {"url": snap["url"], "source_id": snap["source_id"], "tier": snap["tier"],
               "content_hash": snap["content_hash"], "snapshot_id": snapshot_id, "run_id": run_id,
               "organisation": snap["organisation"]}
        summary = store.store_items(conn, checked.items, src)
        conn.execute(
            """UPDATE extraction_runs SET finished_at = now(), ok = true, raw_output = %s, rejected_items = %s,
                 input_tokens = %s, output_tokens = %s WHERE id = %s""",
            (Jsonb(output), Jsonb(checked.rejected), usage["input_tokens"], usage["output_tokens"], run_id),
        )
        conn.commit()
        summary.update(items=len(checked.items), rejected=len(checked.rejected), notes=output.get("notes"))
        log.info("extract %s: %s", snap["url"], summary)
        return summary
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE extraction_runs SET finished_at = now(), ok = false, error = %s WHERE id = %s",
                     (f"{type(exc).__name__}: {exc}"[:2000], run_id))
        conn.commit()
        log.exception("extract %s failed", snap["url"])
        return {"error": str(exc)}


def run(conn, *, force: bool = False, claude_client=None, http_client=None) -> dict:
    """Fetch due pages, then extract every snapshot that still needs it."""
    fetched = fetch.fetch_due(conn, force=force, client=http_client)
    pending = pending_snapshots(conn)
    results = {}
    if pending:
        claude_client = claude_client or extract.make_client()
        for snapshot_id in pending:
            results[snapshot_id] = extract_snapshot(conn, claude_client, snapshot_id)
    return {"fetched": len(fetched), "changed": sum(f.changed for f in fetched),
            "errors": [f"{f.url}: {f.error}" for f in fetched if f.error], "extracted": results}
