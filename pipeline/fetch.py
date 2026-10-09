"""Fetch watched pages, clean them with trafilatura and keep a snapshot only when the main text changed."""
import hashlib
import logging
import re
from dataclasses import dataclass

import httpx
import trafilatura

from pipeline import config

log = logging.getLogger(__name__)

SUPPORTED_METHODS = {"html"}   # html_js (Playwright), rss, wp_json, pdf, email: later phases


@dataclass
class FetchResult:
    source_id: int
    url: str
    http_status: int | None = None
    changed: bool = False
    snapshot_id: int | None = None
    error: str | None = None


def clean_html(html: str) -> tuple[str, str | None]:
    """Main text of the page (no menus, footers, cookie banners) and its 'last modified' date if shown."""
    text = trafilatura.extract(html, include_tables=True, include_comments=False, favor_recall=True) or ""
    meta = trafilatura.extract_metadata(html)
    return text.strip(), (meta.date if meta else None)


def content_hash(text: str) -> str:
    # Whitespace-only edits (re-flowed HTML) are not a change.
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()


def due_sources(conn, *, force: bool = False, source_id: int | None = None) -> list[dict]:
    sql = "SELECT * FROM sources WHERE is_active"
    params: list = []
    if source_id is not None:
        sql += " AND id = %s"
        params.append(source_id)
    elif not force:
        sql += " AND (last_fetched_at IS NULL OR last_fetched_at + check_interval <= now())"
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def fetch_source(conn, client: httpx.Client, source: dict) -> FetchResult:
    result = FetchResult(source_id=source["id"], url=source["url"])
    text = page_modified = None
    if source["method"] not in SUPPORTED_METHODS:
        result.error = f"method {source['method']} not supported yet"
    else:
        try:
            resp = client.get(source["url"])
            result.http_status = resp.status_code
            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
            else:
                text, page_modified = clean_html(resp.text)
                if not text:
                    result.error = "no main text found (page may need JavaScript)"
        except httpx.HTTPError as exc:
            result.error = f"{type(exc).__name__}: {exc}"

    if result.error:
        conn.execute(
            "UPDATE sources SET last_fetched_at = now(), last_http_status = %s, last_error = %s WHERE id = %s",
            (result.http_status, result.error, source["id"]),
        )
        conn.commit()
        log.warning("fetch %s: %s", source["url"], result.error)
        return result

    digest = content_hash(text)
    if digest != source["last_content_hash"]:
        result.changed = True
        row = conn.execute(
            """INSERT INTO snapshots (source_id, http_status, content_hash, clean_text, page_modified)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (source_id, content_hash) DO UPDATE SET fetched_at = now()
               RETURNING id""",
            (source["id"], result.http_status, digest, text, page_modified),
        ).fetchone()
        result.snapshot_id = row["id"]
    conn.execute(
        """UPDATE sources SET last_fetched_at = now(), last_http_status = %s, last_error = NULL,
             last_content_hash = %s,
             last_changed_at = CASE WHEN %s THEN now() ELSE last_changed_at END
           WHERE id = %s""",
        (result.http_status, digest, result.changed, source["id"]),
    )
    conn.commit()
    log.info("fetch %s: %s", source["url"], "changed" if result.changed else "unchanged")
    return result


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": config.USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"},
        timeout=config.FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def fetch_due(conn, *, force: bool = False, source_id: int | None = None,
              client: httpx.Client | None = None) -> list[FetchResult]:
    own = client is None
    client = client or make_client()
    try:
        return [fetch_source(conn, client, s) for s in due_sources(conn, force=force, source_id=source_id)]
    finally:
        if own:
            client.close()
