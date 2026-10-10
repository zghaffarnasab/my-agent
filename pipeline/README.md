# Filmmaker Dashboard Pipeline (Funds and Events)

This folder is separate from the Gmail assistant (`app/`): it has its own Postgres database and runs with its own Compose file. It does not touch the Gmail assistant's containers.

What it does today (first version):

1. Reads the official pages listed in `sources.json` (currently BFI, Doc Society, Whickers and Sheffield DocFest).
2. Extracts the main text of each page with trafilatura and hashes it. A new snapshot is stored only if the text has changed.
3. Sends each new snapshot to Claude with the prompt `prompts/extract-v1.txt`.
4. Checks that every date and amount has a quote that appears **verbatim** in the page text, and that the value itself is inside that quote. Anything that fails this check is recorded in `extraction_runs.rejected_items`.
5. Saves the result in Postgres as a `draft`. Nothing is published automatically.

Not yet included: RSS and newsletters.

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

## Sending to the Wix site (one time)

Only funds and events you **approve** on the film dashboard go to two CMS collections on your Wix site: `FilmFunds` and `FilmEvents`. Drafts never go. If you reject something later, it is removed from Wix too. The sync is one-way: Postgres is the source of truth, and manual edits in the CMS are overwritten on the next run.

1. Create an API key in Wix: Account Settings → API Keys → Generate API Key. Give it the **Wix Data** permissions (manage collections and write items) and select your site.
2. Copy the Site ID from your site's dashboard URL: the part after `/dashboard/`.
3. Add these two lines to `pipeline/.env`:
   ```
   WIX_API_KEY=...
   WIX_SITE_ID=...
   ```
4. First see what would be sent (nothing is sent to Wix):
   ```bash
   sudo docker compose -f pipeline/docker-compose.yml run --rm --build pipeline wix-sync --dry-run
   ```
5. Then send it for real (the first time this also creates the two collections):
   ```bash
   sudo docker compose -f pipeline/docker-compose.yml run --rm pipeline wix-sync
   ```

From then on the daily `run` also does `wix-sync` after reading the pages, so anything you approve today is on Wix the next morning (or right away with the command above).

The collections are not visible on the site until you connect them to a page in the Wix editor (for example a Repeater or a dynamic page). The `displayStatus` field is `expired` for items whose deadlines have passed; filter the page to show only `published`.

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
