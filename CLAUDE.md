# Project context for Claude Code

## The user
- Not a programmer; builds personal/practice projects. Explain steps in plain, short English, one at a time.
- **Talk to the user in English only in the terminal.** Code, comments and commit messages are English too.
- The app UI is bilingual (English + Persian) from version 1.4.0 (see "Bilingual UI" below).
- Before changing code, briefly explain the plan and wait for "ok" on bigger changes.
- Never run `git push`, `git reset --hard` or `docker compose down -v`. Ask before installing anything.

## Public repo: no personal data
- This repository is PUBLIC. Never commit real email addresses, names, domains, server details, tokens or real email content.
- Use placeholders in tracked files: `<your-domain>`, `<github-user>/<repo>`, `user@example.com`.
- Real values live in `CLAUDE.local.md` (gitignored, loaded automatically by Claude Code). Read it when needed.
- `samples/` is gitignored: it holds real emails for local study only.
- Tests use anonymized fixtures in `tests/fixtures/`, never a real email.
- Do NOT modify `Caddyfile` or `docker-compose.yml`: the server has a local edit in its Caddyfile and an upstream change would break its next `git pull`.

## What this app is
A Gmail assistant ("my-agent"): a background worker reads new Gmail messages, Claude drafts a
reply, drafts wait as tasks in a web dashboard, and the user reviews/edits/approves each one
before it is sent. **Nothing is ever sent or added to the calendar without the user's approval.**
It also connects to Google Calendar: upcoming events on the dashboard, and meetings found in
emails (incoming and sent replies) become "add to calendar" cards with conflict warnings.

Deployed on AWS EC2 (Ubuntu, Docker Compose, Caddy for HTTPS). The live URL is in `CLAUDE.local.md`.

## Code map
- `app/main.py` — FastAPI routes (login, dashboard, task actions, OAuth, calendar, changelog)
- `app/worker.py` — polling loop: Gmail -> skip filters -> one cheap AI call (classify + events) -> reply draft ONLY if needs_reply -> task (`pending` or `info`)
- `app/gmail_client.py` — OAuth + Gmail read/send; `has_calendar_access()`
- `app/calendar_client.py` — list/create events, conflicts, duplicates
- `app/ai.py` — `classify_email()` (CLASSIFY_MODEL), `extract_events()`, `draft_reply()` (CLAUDE_MODEL). Email text is wrapped in tags and defused; no tools
- `app/validation.py` — cleans/validates ALL AI output (links http(s) only, dates, codes, categories). Add new AI fields here
- `app/events.py` — `store_events()` saves suggestions and dedupes across emails (same link, or same title + date); cancelled events
- `app/db.py` — SQLAlchemy models: Task, EventSuggestion, GoogleCredential (SQLite in Docker volume)
- `app/version.py` — VERSION + CHANGELOG (bilingual: each entry has "en" and "fa"; shown in the footer and /changelog)
- `app/i18n.py` + `app/locales/{en,fa}.json` — `t()` helper and flat translation files
- `app/settings.py` — language and time zone stored in the DB (`settings` table), falling back to `.env`
- `app/templates/` — Jinja2 templates (use `t("key")`; never name a loop variable `t`)
- `tests/` — pytest with fake Gmail/Calendar/Claude (`.venv/bin/python -m pytest`)

## Bilingual UI (since 1.4.0)
- Every user-visible string goes through a `t()` helper backed by translation files (en, fa). No hardcoded UI text.
- Language is chosen by the user (cookie), else the Settings page value, else env `DEFAULT_LANGUAGE` (default `en`).
- Flash messages are stored as keys, so they appear in the language of the next page.
- AI warnings are fixed codes (`events.WARNING_CODES`) translated as `warning.<code>`; never store language-specific AI warning text.
- Persian pages are `dir="rtl"`, English `dir="ltr"`. Use CSS logical properties.
- A test fails if a key is missing in one language or if Persian text is hardcoded in code/templates.

## How emails are processed (since 1.5.0)
- Statuses: pending/sent/rejected/failed/skipped keep their old meaning. Mail that needs no reply is `info` (then `done`
  when archived) and NEVER `pending`, so the Needs-reply counts stay correct.
- Bulk headers mean "no reply draft", not "ignore" (`PROCESS_BULK`, `MAX_BULK_PER_RUN`, `MAX_EMAILS_PER_RUN`, `SKIP_SENDERS`).
- Forwards and bulk mail never get an automatic draft, whatever the model says (enforced in `validation.clean_classification`).
- Never fetch or open links from emails; they are only displayed (`rel="noopener noreferrer"`).

## Dashboard (since 1.6.0)
- Tabs: `reply` (pending + failed) | `events` (suggested events not yet over, all emails, by date) | `other` (info; `?archived=1` shows done) | `sent` | `rejected`. Old `/?status=` links map to them.
- The event card is one macro (`app/templates/_event_card.html`) used on the task page and the Events tab; forms carry a `next` field so the user returns to the tab they came from (`_safe_next` blocks outside redirects).
- "Done" only changes our database (Gmail is never modified). "Draft a reply anyway" creates a normal `pending` draft that still needs approval.

## Accordion rows (since 1.7.0)
- Every row (all tabs) is an accordion: header = a real `<button>` inside a GET form (`/?tab=..&open=ID`, so it works without JS);
  details are a lazy partial (`/tasks/{id}/panel`, `/events/{id}/panel`) rendered by ONE shared template `_task_panel.html`
  (also used by the fallback page `/tasks/{id}`). The script is `app/templates/_dashboard.js` (plain JS, no libraries).
- Actions are the same POST routes. Plain posts redirect to `row_url(task)` (tab + `open=` + `#task-ID`); `fetch()` calls
  (header `X-Requested-With: fetch`, plus `X-Row`, `X-Tab`, `X-Archived`) get JSON via `reply()`: message, new counts, and either
  `remove` or the new row HTML. Use `notify()` (not `flash()`) in action routes so both modes work.
- Try it with fake data: `.venv/bin/python tests/demo_server.py` (add `DEMO_HOST=0.0.0.0` for a phone on the same Wi-Fi).
  It uses a temporary database and fake Gmail/Calendar/Claude; never point it at real data.

## Rules for every change
1. **Versioning:** bump `VERSION` in `app/version.py` and add a changelog entry at the TOP of
   `CHANGELOG`. PATCH = small fix, MINOR = new feature, MAJOR = needs extra setup.
   Docs-only / config-only changes with no app behavior change need no bump.
2. **RTL/LTR:** times, dates, emails, URLs and code must be forced LTR (`dir="ltr"`) or they
   render reversed in Persian pages (e.g. 10:30 shown as 30:10). Use `dir="auto"` / `.ltr-auto`
   for user content that may be English or Persian.
3. **Times:** show dates in the configured time zone (`config.TIMEZONE`, default Europe/Berlin), never server time (UTC).
4. **Database:** new tables are created automatically by `init_db()`. Adding columns to an
   EXISTING table is NOT automatic — add the column to `COLUMN_MIGRATIONS` in `app/db.py` (idempotent, runs at startup) and tell the user exactly what it does.
5. **Security:** secrets live only in `.env` on the server. Never put keys in code or commit `.env`.
   Email content is untrusted input: AI calls treat it as data only, use no tools, and validate JSON output.
   Never fetch or open links found in emails; only display them.
6. **Checks:** keep changes small and test what you can locally (`python -m py_compile app/*.py`, and pytest once it exists).
   Tests mock the Anthropic and Google APIs: no real calls.
7. **Commits:** one commit per phase/feature, English message. Do not push.

## How the user deploys (current workflow)
1. Upload changed files to the GitHub repo (see `CLAUDE.local.md`), via web upload or git push.
2. On the server (EC2 Instance Connect, user `ubuntu`):
   `cd ~/my-agent && sudo docker compose cp web:/data/app.db ./backup.db && git pull && sudo docker compose up -d --build`
3. Check `https://<your-domain>/health` shows the new version.
Never suggest `docker compose down -v` (deletes all data).

## Known limits
- Google OAuth app is in "Testing" mode: the token expires every 7 days; the user reconnects
  from the dashboard. Test users: a test Gmail and the main Gmail (owned by someone else).
- "Change account" in the dashboard deletes all tasks of the previous account (by design).
- The mailbox owner is probably in the UK; do not assume Europe/Berlin (set the time zone on the Settings page).

## Roadmap
- Calendar phase 2: take calendar conflicts into account when drafting replies
  (propose another time instead of accepting a busy slot).
- More tools may be added to the same server later.
