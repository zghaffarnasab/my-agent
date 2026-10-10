# Filmmaker Dashboard Pipeline (Funds and Events)

This folder is separate from the Gmail assistant (`app/`): it has its own Postgres database and runs with its own Compose file. It does not touch the Gmail assistant's containers.

What it does today (first version):

1. Reads the official pages listed in `sources.json` (currently BFI, Doc Society, Whickers and Sheffield DocFest).
2. Extracts the main text of each page with trafilatura and hashes it. A new snapshot is stored only if the text has changed.
3. Sends each new snapshot to Claude with the prompt `prompts/extract-v1.txt`.
4. Checks that every date and amount has a quote that appears **verbatim** in the page text, and that the value itself is inside that quote. Anything that fails this check is recorded in `extraction_runs.rejected_items`.
5. Saves the result in Postgres as a `draft`. Nothing is published automatically.

Not yet included: Wix sync, a review panel (Review UI), RSS and newsletters.

## Server setup (one time)

```bash
cd ~/my-agent && git pull
cp pipeline/.env.example pipeline/.env
nano pipeline/.env        # fill in POSTGRES_PASSWORD and ANTHROPIC_API_KEY

sudo docker compose -f pipeline/docker-compose.yml up -d db
sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline migrate
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline seed
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline run
sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline status
```

`status` shows record counts, the review queue and upcoming dates. If a page fails (for example with `HTTP 403` or "no main text found"), it probably needs JavaScript and will be read with Playwright in a later phase.

## Review page in the dashboard (one time)

The Gmail dashboard has a "Film dashboard" page where you can see each draft with its quotes and approve or reject it. To turn it on:

1. Restart the database once so it joins the dashboard's network (no data is lost):
   ```bash
   cd ~/my-agent && git pull
   sudo docker compose -f pipeline/docker-compose.yml up -d db
   ```
2. Add this line to the main `.env` file (not `pipeline/.env`). Replace `PASSWORD` with the `POSTGRES_PASSWORD` from `pipeline/.env`:
   ```
   FILMDASH_DATABASE_URL=postgresql://filmdash:PASSWORD@filmdash-db:5432/filmdash
   ```
3. Update the dashboard as usual:
   ```bash
   sudo docker compose cp web:/data/app.db ./backup.db && sudo docker compose up -d --build
   ```

A "Film dashboard" link then appears in the dashboard next to "Settings".

## Daily automatic run

```bash
sudo crontab -e
```

Add this line (runs every day at 6 a.m. server time):

```
0 6 * * * cd /home/ubuntu/my-agent && docker compose -f pipeline/docker-compose.yml run --rm pipeline run >> /var/log/filmdash.log 2>&1
```

By default each page is checked once a week (`check_interval` in the `sources` table). If a page has not changed, Claude is not called and there is no cost.

## After every git pull

```bash
sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline migrate
```

## Viewing the data

```bash
sudo docker compose -f pipeline/docker-compose.yml exec db psql -U filmdash filmdash
```

For example, `SELECT * FROM review_queue;` or `SELECT name, kind, status, date_value, source_quote FROM current_dates d JOIN funds f ON f.id = d.fund_id;`

Backup:

```bash
sudo docker compose -f pipeline/docker-compose.yml exec db pg_dump -U filmdash filmdash > filmdash-backup.sql
```

Never run `docker compose down -v`: it deletes all data.

## Adding a new page

Add the page to `sources.json` and run `seed` again. Use `tier` `official` for the organization's own page, and `aggregator` for listing sites (their dates are never marked "confirmed").

## Tests

Tests that need no database run with the rest of the test suite. To run the full test against an empty Postgres:

```bash
PIPELINE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/filmdash_test .venv/bin/python -m pytest tests/test_pipeline_db.py
```

This test wipes the schema of the database it is given; never point it at a real database. Claude and the web are faked in the tests.
