# Email Reply Assistant (Gmail + Claude)

This app reads new Gmail messages, uses Claude to draft replies, and keeps them in a task queue. You open each task, edit or rewrite the draft if needed, and click "Approve and send" to send the reply in the original email thread. No email is ever sent without your approval.

## Project structure

```
app/
  config.py        Settings from environment variables
  db.py            Database models (tasks and the Google token)
  gmail_client.py  OAuth connection, reading email, sending replies
  ai.py            Drafting replies with Claude
  worker.py        Background process that checks the inbox every few minutes
  main.py          FastAPI web app (dashboard, approval, sending)
  templates/       Dashboard pages
Dockerfile, docker-compose.yml, Caddyfile
```

## 1. Create an OAuth client in Google Cloud

1. Go to https://console.cloud.google.com and create a new project.
2. Under APIs & Services → Library, enable the **Gmail API**.
3. On the OAuth consent screen, set the user type to External (or Internal if you have Google Workspace), and add your own email address under Test users.
4. Under Credentials → Create credentials → OAuth client ID, choose **Web application** and add these redirect URIs:
   - `http://localhost:8000/auth/callback` for testing on your own computer
   - `https://mail.example.com/auth/callback` with your real domain, for the server
5. Put the Client ID and Client Secret in the `.env` file.

Important: if the Google app is in Testing mode with the External user type, Google revokes the token every 7 days and you will need to click "Connect Gmail" on the dashboard again. There are two ways to remove this limit completely: use a Google Workspace account with the Internal user type, or publish the app (which requires a Google review for Gmail access).

## 2. Run on your own computer

```bash
cp .env.example .env
# Fill in the values and set BASE_URL=http://localhost:8000
docker compose up --build web worker
```

Then open http://localhost:8000, sign in with the dashboard password, and click "Connect Gmail".

## 3. Deploy on AWS (EC2)

1. Create an Ubuntu EC2 instance (a t3.small is enough). In the Security Group, open ports 22, 80 and 443.
2. Attach an Elastic IP so the IP address stays fixed, and point your domain's A record (for example `mail.example.com`) to that IP.
3. Install Docker on the server:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # then log out and back in once
   ```
4. Copy the project to the server (with git or scp), create the `.env` file, and set `BASE_URL=https://mail.example.com`.
5. Replace the domain in the `Caddyfile` with your own. Caddy obtains the HTTPS certificate automatically.
6. Start it:
   ```bash
   docker compose up -d --build
   docker compose logs -f worker
   ```

Because of `restart: always`, everything comes back up automatically if the app crashes or the server restarts.

## Google Calendar

The app also connects to Google Calendar: events for the next few days are shown at the top of the dashboard, and meetings found in incoming emails or in your sent replies appear as "Add to calendar" cards on each task's page. No event is added to your calendar without your approval. If a meeting time clashes with another event, the card shows a warning.

To enable it: turn on the **Google Calendar API** in Google Cloud, and after updating the app, click "Enable calendar" on the dashboard to grant calendar permission.

Optional settings in `.env`: `TIMEZONE` for your time zone (default `Europe/Berlin`), `UPCOMING_DAYS` for the number of days shown on the dashboard (default 7), and `CALENDAR_ID` if you want events added to a calendar other than your primary one.

## Useful settings in `.env`

`GMAIL_QUERY` controls which emails get a reply. By default it picks up unread emails from the last two days (to exclude a category, add something like `-category:promotions`). If you usually open emails in Gmail before the app sees them, remove `is:unread`. You can also use `label:` to target a single label.

`REPLY_STYLE`, `OWNER_NAME` and `EMAIL_SIGNATURE` set the tone and signature of replies. Claude always replies in the sender's language, and marks any information it does not have with square brackets, such as `[meeting time]`, for you to fill in.

Each email is read and categorized once by an inexpensive model (`CLASSIFY_MODEL`). A draft is written only when someone is waiting for a reply; everything else (newsletters, receipts, notifications, forwards) appears under "Other emails" with a summary and any events it mentions. Your own emails and system messages are ignored. Set `PROCESS_BULK=false` to stop reading newsletters.

## Security

Never commit keys to git (`.env` is in `.gitignore`). Use long, random values for `SECRET_KEY` and `DASHBOARD_PASSWORD`. For a more serious setup, keep keys in AWS Secrets Manager and use RDS instead of SQLite; you only need to change `DATABASE_URL`.

## Ideas for the next version

Telegram or email notifications when a new task arrives, AI-based email prioritization, and learning your tone from replies you have edited before.
