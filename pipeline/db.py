"""Postgres connection and migrations (plain SQL files in pipeline/sql, applied in name order)."""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from pipeline import config

SQL_DIR = Path(__file__).parent / "sql"


def connect(url: str | None = None) -> psycopg.Connection:
    url = url or config.require("PIPELINE_DATABASE_URL", config.DATABASE_URL)
    return psycopg.connect(url, row_factory=dict_row)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply every pipeline/sql/*.sql file that has not run yet. Safe to run again."""
    conn.autocommit = True
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                      name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())""")
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied = []
    for path in sorted(SQL_DIR.glob("*.sql")):
        if path.name in done:
            continue
        # Each file wraps itself in BEGIN/COMMIT, so a failing file leaves nothing half-applied.
        conn.execute(path.read_text())
        conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    conn.autocommit = False
    return applied
