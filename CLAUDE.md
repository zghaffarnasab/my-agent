# Project context for Claude Code

## The user
- Not a programmer; builds personal/practice projects. Explain steps simply, one at a time.
- **Always reply in Persian (Farsi).** Code, comments and commit messages stay in English.
- Before changing code, briefly explain the plan in Persian and wait for "ok" on bigger changes.

## What this app is
A Gmail assistant ("my-agent"): a background worker reads new Gmail messages, Claude drafts a
reply, drafts wait as tasks in a web dashboard, and the user reviews/edits/approves each one
before it is sent. **Nothing is ever sent or added to the calendar without the user's approval.**
It also connects to Google Calendar: upcoming events on the dashboard, and meetings found in
emails (incoming and sent replies) become "add to calendar" cards with conflict warnings.

Live at https://agent.prometheefilms.com (AWS EC2, Ubuntu, Docker Compose, Caddy for HTTPS).

## Code map
- `app/main.py` — FastAPI routes (login, dashboard, task actions, OAuth, calendar, changelog)
- `app/worker.py` — polling loop: Gmail -> draft -> task, then event extraction
- `app/gmail_client.py` — OAuth + Gmail read/send; `has_calendar_access()`
- `app/calendar_client.py` — list/create events, conflicts, duplicates
- `app/ai.py` — `draft_reply()` and `extract_events()` (Claude API)
- `app/events.py` — validates extracted events and stores `EventSuggestion` rows
- `app/db.py` — SQLAlchemy models: Task, EventSuggestion, GoogleCredential (SQLite in Docker volume)
- `app/version.py` — VERSION + CHANGELOG (Persian), shown in the page footer and /changelog
- `app/templates/` — Jinja2, Persian RTL UI (Vazirmatn font)

## Rules for every change
1. **Versioning:** bump `VERSION` in `app/version.py` and add a Persian changelog entry at the
   TOP of `CHANGELOG`. PATCH = small fix, MINOR = new feature, MAJOR = needs extra setup.
2. **RTL UI:** pages are `dir="rtl"`. Times, dates, emails, URLs and code must be forced LTR
   (`dir="ltr"`) or they render reversed (e.g. 10:30 shown as 30:10). Use `dir="auto"` /
   `.ltr-auto` for user content that may be English or Persian.
3. **Times:** show dates in `config.TIMEZONE` (default Europe/Berlin), never server time (UTC).
4. **Database:** new tables are created automatically by `init_db()`. Adding columns to an
   EXISTING table is NOT automatic — tell the user and provide a migration step.
5. Secrets live only in `.env` on the server. Never put keys in code or commit `.env`.
6. Keep changes small and test what you can locally (e.g. `python -m py_compile app/*.py`).

## How the user deploys (current workflow)
1. Upload changed files to the GitHub repo `zghaffarnasab/my-agent` (web upload, or git push).
2. On the server (EC2 Instance Connect, user `ubuntu`):
   `cd ~/my-agent && sudo docker compose cp web:/data/app.db ./backup.db && git pull && sudo docker compose up -d --build`
3. Check `https://agent.prometheefilms.com/health` shows the new version.
Never suggest `docker compose down -v` (deletes all data).

## Known limits
- Google OAuth app is in "Testing" mode: the token expires every 7 days; the user reconnects
  from the dashboard. Test users: a test Gmail and the main Gmail (owned by someone else).
- "Change account" in the dashboard deletes all tasks of the previous account (by design).

## Roadmap
- Phase 2 of calendar: take calendar conflicts into account when drafting replies
  (propose another time instead of accepting a busy slot).
- More tools may be added to the same server later.
