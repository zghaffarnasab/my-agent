"""Seed organisations and watched pages from pipeline/sources.json (idempotent)."""
import json
from pathlib import Path

SOURCES_FILE = Path(__file__).parent / "sources.json"


def load(path: Path = SOURCES_FILE) -> dict:
    return json.loads(path.read_text())


def org_id(conn, name: str | None, website: str | None = None) -> int | None:
    if not name:
        return None
    row = conn.execute(
        """INSERT INTO organisations (name, website) VALUES (%s, %s)
           ON CONFLICT (name) DO UPDATE SET website = coalesce(organisations.website, EXCLUDED.website)
           RETURNING id""",
        (name, website),
    ).fetchone()
    return row["id"]


def seed(conn, data: dict | None = None) -> int:
    data = data or load()
    for org in data.get("organisations", []):
        org_id(conn, org["name"], org.get("website"))
    count = 0
    for s in data["sources"]:
        conn.execute(
            """INSERT INTO sources (url, organisation_id, title, tier, method, feeds_kind)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (url) DO UPDATE SET organisation_id = EXCLUDED.organisation_id,
                 title = EXCLUDED.title, tier = EXCLUDED.tier, method = EXCLUDED.method,
                 feeds_kind = EXCLUDED.feeds_kind""",
            (s["url"], org_id(conn, s.get("organisation")), s.get("title"), s["tier"], s["method"],
             s.get("feeds_kind")),
        )
        count += 1
    conn.commit()
    return count
