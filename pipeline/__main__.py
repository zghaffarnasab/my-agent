"""Command line: python -m pipeline <command>

  migrate            create / update the Postgres tables (safe to run again)
  seed               add the watched pages from pipeline/sources.json
  fetch [--force]    download due pages and keep a snapshot when the text changed
  extract            send new snapshots to Claude and store the results as drafts
  run [--force]      fetch + extract + wix-sync (what the daily cron job runs)
  wix-sync [--dry-run]  send published funds/events to the Wix CMS (only if WIX_API_KEY is set)
  status             counts and the review queue
"""
import argparse
import json
import logging

from pipeline import db, fetch, runner, sources


def status(conn) -> None:
    for label, sql in [
        ("sources", "SELECT count(*) AS n FROM sources WHERE is_active"),
        ("sources with errors", "SELECT count(*) AS n FROM sources WHERE last_error IS NOT NULL"),
        ("snapshots", "SELECT count(*) AS n FROM snapshots"),
        ("funds (draft)", "SELECT count(*) AS n FROM funds WHERE status = 'draft'"),
        ("events (draft)", "SELECT count(*) AS n FROM events WHERE status = 'draft'"),
        ("current dates", "SELECT count(*) AS n FROM current_dates"),
        ("date conflicts", "SELECT count(*) AS n FROM date_conflicts"),
        ("failed extractions", """SELECT count(*) AS n FROM (
             SELECT DISTINCT ON (source_id) id FROM snapshots ORDER BY source_id, fetched_at DESC) latest
           WHERE NOT EXISTS (SELECT 1 FROM extraction_runs r WHERE r.snapshot_id = latest.id AND r.ok)
             AND EXISTS (SELECT 1 FROM extraction_runs r WHERE r.snapshot_id = latest.id)"""),
    ]:
        print(f"{label:22} {conn.execute(sql).fetchone()['n']}")
    print("\nReview queue:")
    for r in conn.execute("SELECT * FROM review_queue ORDER BY record_kind, name"):
        print(f"  [{r['record_kind']}] {r['name']}  ({r['status']})")
    print("\nUpcoming dates (all statuses, drafts included):")
    for r in conn.execute(
        """SELECT coalesce(f.name, e.name) AS name, d.kind, d.label, d.status, d.date_value, d.approx_text
           FROM current_dates d LEFT JOIN funds f ON f.id = d.fund_id LEFT JOIN events e ON e.id = d.event_id
           WHERE d.date_value >= current_date OR d.date_value IS NULL ORDER BY d.date_value NULLS LAST"""):
        when = r["date_value"] or r["approx_text"] or "?"
        print(f"  {when}  {r['name']}: {r['label'] or r['kind']} [{r['status']}]")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["migrate", "seed", "fetch", "extract", "run", "wix-sync", "status"])
    parser.add_argument("--force", action="store_true", help="fetch every page, even if checked recently")
    parser.add_argument("--source", type=int, help="fetch only this source id")
    parser.add_argument("--dry-run", action="store_true", help="wix-sync: show what would be sent, call nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with db.connect() as conn:
        if args.command == "migrate":
            print("applied:", db.migrate(conn) or "nothing new")
        elif args.command == "seed":
            print("sources:", sources.seed(conn))
        elif args.command == "fetch":
            for r in fetch.fetch_due(conn, force=args.force, source_id=args.source):
                print(f"{'ERROR  ' if r.error else 'CHANGED' if r.changed else 'same   '} {r.url} {r.error or ''}")
        elif args.command == "extract":
            from pipeline import extract
            pending = runner.pending_snapshots(conn)
            client = extract.make_client() if pending else None
            for snapshot_id in pending:
                print(snapshot_id, json.dumps(runner.extract_snapshot(conn, client, snapshot_id), default=str))
            if not pending:
                print("nothing to extract")
        elif args.command == "run":
            print(json.dumps(runner.run(conn, force=args.force), indent=2, default=str))
        elif args.command == "wix-sync":
            from pipeline import wix
            print(json.dumps(wix.sync(conn, dry_run=args.dry_run), indent=2, ensure_ascii=False, default=str))
        elif args.command == "status":
            status(conn)


if __name__ == "__main__":
    main()
