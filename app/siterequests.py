"""Requests sent through the website form, matched to published funds and events.

The website (a separate app) inserts rows into `site_requests` in the same Postgres as the pipeline.
This module only reads the pipeline tables, and on `site_requests` it only changes `status` and the
`profile` JSON (suggestions, the owner's choices, the offer email, submissions and their replies).
Nothing reaches the visitor or an organiser without the owner pressing a button.

The visitor answers the offer on the website's confirmation page (`/confirm/<token>`, token and options
written here into `profile.confirm`); the website stores the answer in `site_confirmations`, which the worker
copies back (`sync_confirmations`). Email registrations are sent from the company address with the visitor
in copy, and replies are read over IMAP without marking anything as read (`poll_replies`). Registration on
other websites is still done by hand.
"""
import email
import email.policy
import imaplib
import logging
import re
import secrets
import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr
from urllib.parse import quote

import psycopg
from psycopg.types.json import Jsonb

from app import ai, config, countries, filmdash, i18n, settings, validation

log = logging.getLogger(__name__)

# new -> matched (suggestions ready) -> offered (email sent to the visitor) -> confirmed (the visitor said yes)
# -> registered (every chosen option is done). closed = no fit, declined or spam.
STATUSES = ("new", "matched", "offered", "confirmed", "registered", "closed")
NEEDS = ("festival", "fund", "workshop", "collab", "advice")
MANUAL_NEEDS = ("collab", "advice")          # nothing in the database to match against

# Same split as the website's call sheets (OpportunityMapper.WORKSHOP_TYPES).
EVENT_TYPES = {
    "festival": ("festival", "market", "award"),
    "workshop": ("lab", "workshop", "pitch", "talent_programme"),
}
# Website "stage" -> pipeline fund stages that fit it.
STAGE_FIT = {
    "none": ("talent", "development"), "idea": ("development", "talent"), "development": ("development",),
    "production": ("production",), "post": ("post_production",),
    "finished": ("distribution", "festival_travel"),
}
MAX_CANDIDATES = 12       # sent to the AI to choose from
MAX_PICKS = 5
CONFIRM_DAYS = 30         # how long the confirmation link works


class NotFound(Exception):
    pass


def enabled() -> bool:
    return filmdash.enabled()


def _connect():
    conn = filmdash._connect()
    try:
        conn.execute("SELECT 1 FROM site_requests LIMIT 0")
    except psycopg.errors.UndefinedTable as exc:
        conn.close()
        raise filmdash.Unavailable("no table") from exc
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Reading ----------

def overview(status: str) -> tuple[list[dict], dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, created_at, status, lang, name, email, country, film_title, film_type, stage, needs,
                      left(message, 160) AS preview
               FROM site_requests WHERE status = %s ORDER BY created_at DESC LIMIT 200""",
            (status,),
        ).fetchall()
        counts = {s: 0 for s in STATUSES}
        for r in conn.execute("SELECT status, count(*) AS n FROM site_requests GROUP BY 1"):
            if r["status"] in counts:
                counts[r["status"]] = r["n"]
    return rows, counts


def get(request_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM site_requests WHERE id = %s", (request_id,)).fetchone()
    if row is None:
        return None
    row = dict(row)
    row["profile"] = row.get("profile") or {}
    return row


# ---------- Matching ----------

_FUNDS_SQL = """
SELECT 'fund' AS kind, f.id, f.name, f.strand AS sub, o.name::text AS org, f.uk_eligible::text AS uk_eligible,
       f.open_to, f.stages::text[] AS stages, f.forms, f.genres, f.summary, f.amount_min, f.amount_max,
       f.amount_currency,
       NULL::numeric AS fee_min, NULL::numeric AS fee_max, NULL::text AS fee_currency, NULL::text AS event_type,
       coalesce(f.apply_url, f.source_url::text) AS url, NULL::text AS platform, f.apply_email,
       nd.d AS next_date
FROM funds f
LEFT JOIN organisations o ON o.id = f.organisation_id
LEFT JOIN LATERAL (SELECT min(d.date_value) AS d FROM current_dates d
                   WHERE d.fund_id = f.id AND d.date_value >= current_date) nd ON true
WHERE f.status = 'published' AND f.is_accepting IS DISTINCT FROM false
  AND (nd.d IS NOT NULL OR NOT EXISTS (SELECT 1 FROM current_dates d WHERE d.fund_id = f.id AND d.date_value IS NOT NULL))
"""

_EVENTS_SQL = """
SELECT 'event' AS kind, e.id, e.name, e.edition AS sub, o.name::text AS org, e.uk_eligible::text AS uk_eligible,
       e.open_to, '{}'::text[] AS stages, '{}'::text[] AS forms, e.genres, e.summary, NULL::numeric AS amount_min,
       NULL::numeric AS amount_max, NULL::text AS amount_currency, e.fee_min, e.fee_max, e.fee_currency::text,
       e.event_type::text AS event_type, coalesce(e.submit_url, e.source_url::text) AS url,
       e.submit_platform::text AS platform, NULL::text AS apply_email, nd.d AS next_date
FROM events e
LEFT JOIN organisations o ON o.id = e.organisation_id
LEFT JOIN LATERAL (SELECT min(d.date_value) AS d FROM current_dates d
                   WHERE d.event_id = e.id AND d.date_value >= current_date) nd ON true
WHERE e.status = 'published' AND e.event_type::text = ANY(%s)
  AND (nd.d IS NOT NULL OR NOT EXISTS (SELECT 1 FROM current_dates d WHERE d.event_id = e.id AND d.date_value IS NOT NULL))
"""


def _score(rec: dict, req: dict, today: date) -> int | None:
    """Rule-based fit. None = clearly not a fit (dropped before the AI sees it)."""
    score = 0
    country = countries.code(req.get("country"))
    in_uk = country == "GB"
    if rec["uk_eligible"] == "no" and in_uk:
        return None
    if rec["uk_eligible"] == "yes" and in_uk:
        score += 1
    open_to = countries.covers(rec["open_to"], country)
    if open_to is False:
        return None
    if open_to and not in_uk:
        score += 1
    film_type = req.get("film_type") or ""
    tags = {t.lower() for t in (rec["forms"] or []) + (rec["genres"] or [])}
    if film_type and film_type != "other" and tags:
        score += 2 if film_type in tags or (film_type == "series" and "tv" in tags) else -1
    stage = req.get("stage") or ""
    if rec["kind"] == "fund" and stage and rec["stages"]:
        if set(STAGE_FIT.get(stage, ())) & set(rec["stages"]):
            score += 2
        else:
            return None
    if rec["next_date"] and rec["next_date"] <= today + timedelta(days=120):
        score += 1
    return score


def _money(rec: dict) -> str:
    if rec["kind"] == "fund":
        return filmdash._money(rec["amount_min"], rec["amount_max"], rec["amount_currency"])
    return filmdash._money(rec["fee_min"], rec["fee_max"], rec["fee_currency"])


def candidates(conn, req: dict) -> list[dict]:
    """Published, still-open records that fit the request's needs, best rule score first."""
    needs = [n for n in (req.get("needs") or []) if n in NEEDS] or ["festival", "fund", "workshop"]
    rows = []
    if "fund" in needs:
        rows += conn.execute(_FUNDS_SQL).fetchall()
    types = [t for n in needs for t in EVENT_TYPES.get(n, ())]
    if types:
        rows += conn.execute(_EVENTS_SQL, (types,)).fetchall()
    today = date.today()
    scored = []
    for r in rows:
        s = _score(r, req, today)
        if s is not None:
            scored.append((s, r))
    scored.sort(key=lambda p: (-p[0], p[1]["next_date"] or date.max, p[1]["name"]))
    out = []
    for s, r in scored[:MAX_CANDIDATES]:
        out.append({
            "key": f"{r['kind']}:{r['id']}", "kind": r["kind"], "id": r["id"], "name": r["name"],
            "sub": r["sub"] or "", "org": r["org"] or "", "type": r["event_type"] or "fund",
            "summary": r["summary"] or "", "url": r["url"] or "", "platform": r["platform"] or "",
            "apply_email": r["apply_email"] or "", "money": _money(r),
            "next_date": r["next_date"].isoformat() if r["next_date"] else "", "score": s,
        })
    return out


def _pick_reasons(req: dict, cands: list[dict]) -> list[dict]:
    """Let the AI choose and explain; fall back to the rule order when it fails."""
    if not cands:
        return []
    try:
        picks = ai.rank_request_matches(request=req, candidates=cands, max_picks=MAX_PICKS)
    except Exception:
        log.exception("Ranking site request %s failed; using the rule order", req["id"])
        picks = [{"key": c["key"], "reason": ""} for c in cands[:MAX_PICKS]]
    by_key = {c["key"]: c for c in cands}
    return [{**by_key[p["key"]], "reason": p["reason"], "chosen": True, "registered": False}
            for p in picks if p["key"] in by_key]


def match(request_id: int) -> dict:
    """(Re)build the suggestions of one request and move it to `matched`."""
    with _connect() as conn:
        req = conn.execute("SELECT * FROM site_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
        if req is None:
            raise NotFound(request_id)
        picks = _pick_reasons(req, candidates(conn, req))
        profile = dict(req["profile"] or {})
        profile.update({
            "matched_at": _now(), "picks": picks,
            "manual_needs": [n for n in (req["needs"] or []) if n in MANUAL_NEEDS],
        })
        profile.pop("offer", None)
        conn.execute("UPDATE site_requests SET status = 'matched', profile = %s WHERE id = %s",
                     (Jsonb(profile), request_id))
        conn.commit()
    return profile


def match_new(limit: int) -> int:
    """Worker step: suggestions for the newest unmatched requests."""
    if not enabled():
        return 0
    try:
        with _connect() as conn:
            ids = [r["id"] for r in conn.execute(
                "SELECT id FROM site_requests WHERE status = 'new' AND profile IS NULL ORDER BY created_at LIMIT %s",
                (limit,))]
    except filmdash.Unavailable:
        return 0
    for request_id in ids:
        try:
            match(request_id)
        except Exception:
            log.exception("Matching site request %s failed", request_id)
    return len(ids)


# ---------- The owner's choices and the offer email ----------

def _save(conn, request_id: int, profile: dict, status: str | None = None) -> None:
    if status:
        conn.execute("UPDATE site_requests SET profile = %s, status = %s WHERE id = %s",
                     (Jsonb(profile), status, request_id))
    else:
        conn.execute("UPDATE site_requests SET profile = %s WHERE id = %s", (Jsonb(profile), request_id))
    conn.commit()


def _load(conn, request_id: int) -> dict:
    req = conn.execute("SELECT * FROM site_requests WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
    if req is None:
        raise NotFound(request_id)
    return req


def _raw(lang: str, key: str, **params) -> str:
    """Translated text for an email: no direction marks around the values (they would break links)."""
    text = i18n.messages(lang).get(key) or i18n.messages("en")[key]
    return text.format(**params) if params else text


def _how(pick: dict) -> str:
    if organiser_address(pick):
        return "email"
    return "filmfreeway" if pick.get("platform") == "filmfreeway" else "site"


def _how_to_register(lang: str, pick: dict) -> str:
    return _raw(lang, "rqmail.how_" + _how(pick))


def confirm_url(profile: dict) -> str:
    token = (profile.get("confirm") or {}).get("token")
    if not (token and config.REQUESTS_CONFIRM_URL):
        return ""
    return f"{config.REQUESTS_CONFIRM_URL.rstrip('/')}/{token}"


def draft_offer(req: dict, picks: list[dict], note: str, link: str = "") -> dict:
    lang = i18n.normalize(req["lang"])
    film = _raw(lang, "rqmail.film", title=req["film_title"]) if req["film_title"] else ""
    lines = [_raw(lang, "rqmail.hello", name=req["name"]), "", _raw(lang, "rqmail.intro", film=film), ""]
    for n, p in enumerate(picks, 1):
        title = p["name"] + (f" · {p['sub']}" if p["sub"] else "") + (f" ({p['org']})" if p["org"] else "")
        lines.append(f"{n}. {title}")
        if p["reason"]:
            lines.append(f"   {p['reason']}")
        facts = []
        if p["next_date"]:
            # Left-to-right marks keep the date in order inside a right-to-left line.
            when = f"‎{p['next_date']}‎" if i18n.DIRECTION[lang] == "rtl" else p["next_date"]
            facts.append(_raw(lang, "rqmail.next_date", date=when))
        if p["money"]:
            facts.append(_raw(lang, "rqmail.amount" if p["kind"] == "fund" else "rqmail.fee", money=p["money"]))
        if facts:
            lines.append("   " + " · ".join(facts))
        lines.append(f"   {_how_to_register(lang, p)}")
        if p["url"] and not p["url"].lower().startswith("mailto:"):
            lines.append(f"   {p['url']}")
        lines.append("")
    if note.strip():
        lines += [note.strip(), ""]
    if link:
        lines += [_raw(lang, "rqmail.next_step_link"), link, ""]
    else:
        lines += [_raw(lang, "rqmail.next_step"), ""]
    lines += [_raw(lang, "rqmail.closing"), config.REQUESTS_SIGNATURE or config.OWNER_NAME]
    return {"subject": _raw(lang, "rqmail.subject"), "body": "\n".join(lines).strip()}


def _confirm_snapshot(profile: dict, chosen: list[dict]) -> dict:
    """What the website's confirmation page shows. The token stays the same when the choice changes."""
    old = profile.get("confirm") or {}
    expires = datetime.now(timezone.utc) + timedelta(days=CONFIRM_DAYS)
    return {
        "token": old.get("token") or secrets.token_urlsafe(32),
        "expires_at": expires.isoformat(timespec="seconds"),
        "options": [{"key": p["key"], "name": p["name"] + (f" · {p['sub']}" if p["sub"] else ""), "org": p["org"],
                     "next_date": p["next_date"], "money": p["money"],
                     "url": "" if p["url"].lower().startswith("mailto:") else p["url"], "how": _how(p)}
                    for p in chosen],
    }


def choose(request_id: int, keys: list[str], note: str) -> dict:
    """Keep only the options the owner ticked and write the offer email draft (with the confirmation link)."""
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        picks = profile.get("picks", [])
        for p in picks:
            p["chosen"] = p["key"] in keys
        profile["note"] = note.strip()[:2000]
        chosen = [p for p in picks if p["chosen"]]
        if chosen:
            profile["confirm"] = _confirm_snapshot(profile, chosen)
            profile["offer"] = draft_offer(req, chosen, profile["note"], confirm_url(profile))
        else:
            profile["offer"] = None
        _save(conn, request_id, profile)
    return profile


def mail_configured() -> bool:
    return bool(config.REQUESTS_MAIL_HOST and config.REQUESTS_MAIL_FROM)


def _send_mail(to: str, subject: str, body: str, cc: str = "") -> str:
    """Send one plain-text email from the company address; returns its Message-ID."""
    msg = EmailMessage()
    msg["From"] = formataddr((config.REQUESTS_SIGNATURE or "", config.REQUESTS_MAIL_FROM))
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=config.REQUESTS_MAIL_FROM.rsplit("@", 1)[-1])
    msg.set_content(body)
    context = ssl.create_default_context()
    if config.REQUESTS_MAIL_PORT == 465:
        server = smtplib.SMTP_SSL(config.REQUESTS_MAIL_HOST, 465, context=context, timeout=20)
    else:
        server = smtplib.SMTP(config.REQUESTS_MAIL_HOST, config.REQUESTS_MAIL_PORT, timeout=20)
        server.starttls(context=context)
    with server:
        if config.REQUESTS_MAIL_USER:
            server.login(config.REQUESTS_MAIL_USER, config.REQUESTS_MAIL_PASSWORD)
        server.send_message(msg)
    return msg["Message-ID"]


def send_offer(request_id: int, subject: str, body: str, *, manual: bool) -> None:
    """Send the (edited) offer to the visitor, or record that the owner sent it from their own mail."""
    subject, body = subject.strip()[:300], body.strip()[:20000]
    with _connect() as conn:
        req = _load(conn, request_id)
        if not manual:
            _send_mail(req["email"], subject, body)
        profile = dict(req["profile"] or {})
        profile["offer"] = {"subject": subject, "body": body, "sent_at": _now(),
                            "via": "manual" if manual else "smtp"}
        _save(conn, request_id, profile, "offered")


def mailto(to: str, subject: str, body: str, cc: str = "") -> str:
    extra = f"&cc={quote(cc, safe='@')}" if cc else ""
    return f"mailto:{quote(to, safe='@')}?subject={quote(subject)}{extra}&body={quote(body)}"


def organiser_address(pick: dict) -> str:
    if pick.get("apply_email"):
        return pick["apply_email"]
    url = pick.get("url") or ""
    return url[len("mailto:"):].split("?")[0] if url.lower().startswith("mailto:") else ""


# ---------- The visitor's answer from the website ----------

def sync_confirmations(limit: int = 50) -> int:
    """Worker step: copy new answers from the website's confirmation page into the requests."""
    if not enabled():
        return 0
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT c.* FROM site_confirmations c JOIN site_requests r ON r.id = c.request_id
                   WHERE (r.profile->>'confirmation_id') IS DISTINCT FROM c.id::text ORDER BY c.id LIMIT %s""",
                (limit,)).fetchall()
            for row in rows:
                _apply_confirmation(conn, row)
    except filmdash.Unavailable:
        return 0
    except psycopg.errors.UndefinedTable:
        return 0                      # the website has not created site_confirmations yet
    return len(rows)


def _apply_confirmation(conn, row: dict) -> None:
    req = _load(conn, row["request_id"])
    profile = dict(req["profile"] or {})
    choices = set(row["choices"] or [])
    for p in profile.get("picks", []):
        p["chosen"] = p["key"] in choices
    profile.update({
        "confirmation_id": str(row["id"]), "confirmed_at": row["created_at"].isoformat(timespec="seconds"),
        "materials": row["materials"] or {}, "consent_version": row["consent_version"],
    })
    status = "confirmed" if req["status"] in ("matched", "offered") else None
    _save(conn, req["id"], profile, status)


# ---------- Registration by email, sent for the visitor ----------

MATERIAL_FIELDS = ("runtime", "synopsis", "screenerUrl", "screenerPassword", "posterUrl", "bio", "website", "notes")
_TAG_RE = re.compile(r"\[PF-(\d+)-([ef])(\d+)\]")


def tag(request_id: int, key: str) -> str:
    """Put in every registration subject, so replies find their way back even without threading headers."""
    kind, _, rec_id = key.partition(":")
    return f"[PF-{request_id}-{kind[0]}{rec_id}]"


def _key_from_tag(match) -> tuple[int, str]:
    return int(match.group(1)), ("fund" if match.group(2) == "f" else "event") + ":" + match.group(3)


def draft_registration(req: dict, pick: dict) -> dict:
    """The registration email to the organiser, in English, with the film materials the visitor sent."""
    to = organiser_address(pick)
    if not to:
        return {}
    profile = req["profile"] or {}
    materials = profile.get("materials") or {}
    rows = [("name", req["name"]), ("email", req["email"]), ("country", req["country"]),
            ("film", req["film_title"]), ("film_type", req["film_type"]), ("stage", req["stage"])]
    rows += [(f, materials.get(f)) for f in MATERIAL_FIELDS]
    facts = "\n".join(
        f"{_raw('en', 'rqreg.' + k)}:\n{v}" if k in ("synopsis", "bio", "notes") else f"{_raw('en', 'rqreg.' + k)}: {v}"
        for k, v in rows if v)
    body = _raw("en", "rqreg.body", event=pick["name"] + (f" · {pick['sub']}" if pick["sub"] else ""),
                facts=facts, email=req["email"])
    body += "\n\n" + (config.REQUESTS_SIGNATURE or config.OWNER_NAME)
    subject = _raw("en", "rqreg.subject", event=pick["name"], name=req["name"]) + " " + tag(req["id"], pick["key"])
    return {"to": to, "cc": req["email"], "subject": subject, "body": body.strip()}


def registration_mailto(req: dict, pick: dict) -> str:
    """The same email opened in the owner's own mail app (when SMTP is not set up)."""
    draft = draft_registration(req, pick)
    return mailto(draft["to"], draft["subject"], draft["body"], draft["cc"]) if draft else ""


def form_pack(req: dict, pick: dict) -> list[tuple[str, str]]:
    """What an organiser's online form usually asks, ready to copy: the owner fills that form by hand.

    Labels stay English (the forms are), values are what the visitor sent. No bot fills any form.
    """
    materials = (req["profile"] or {}).get("materials") or {}
    rows = [("name", req["name"]), ("email", req["email"]), ("country", req["country"]),
            ("film", req["film_title"]), ("film_type", req["film_type"]), ("stage", req["stage"])]
    rows += [(f, materials.get(f)) for f in MATERIAL_FIELDS]
    return [(k, str(v).strip()) for k, v in rows if v and str(v).strip()]


def record_form_registration(request_id: int, key: str, ref: str, note: str) -> None:
    """The owner registered on the organiser's own site: keep where, when and the reference, for tracking."""
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        pick = next((p for p in profile.get("picks", []) if p["key"] == key and p.get("chosen")), None)
        if pick is None or organiser_address(pick):
            raise NotFound(key)
        pick["submission"] = {"manual": True, "via": _how(pick), "ref": ref.strip()[:200],
                              "note": note.strip()[:2000], "sent_at": _now()}
        pick["registered"] = True
        _save(conn, request_id, profile, _finish_status(req, profile))


def set_outcome(request_id: int, key: str, outcome: str) -> None:
    """For registrations made on a website: the owner records what the organiser said (no email to read)."""
    if outcome not in validation.REPLY_OUTCOMES:
        raise ValueError(outcome)
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        pick = next((p for p in profile.get("picks", []) if p["key"] == key and p.get("submission")), None)
        if pick is None:
            raise NotFound(key)
        pick["outcome"] = outcome
        pick["outcome_at"] = _now()
        _save(conn, request_id, profile)


def _finish_status(req: dict, profile: dict) -> str:
    chosen = [p for p in profile.get("picks", []) if p.get("chosen")]
    if chosen and all(p.get("registered") for p in chosen):
        return "registered"
    return "confirmed" if req["status"] == "registered" else req["status"]


def send_registration(request_id: int, key: str, subject: str, body: str) -> None:
    """Send the (edited) registration to the organiser from the company address, the visitor in copy."""
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        pick = next((p for p in profile.get("picks", []) if p["key"] == key and p.get("chosen")), None)
        to = organiser_address(pick) if pick else ""
        if not to:
            raise NotFound(key)
        subject = subject.strip()[:300]
        if tag(request_id, key) not in subject:
            subject = f"{subject} {tag(request_id, key)}"
        body = body.strip()[:20000]
        message_id = _send_mail(to, subject, body, cc=req["email"])
        pick["submission"] = {"to": to, "subject": subject, "body": body, "message_id": message_id,
                              "sent_at": _now()}
        pick["registered"] = True
        _save(conn, request_id, profile, _finish_status(req, profile))


def set_registered(request_id: int, key: str, done: bool) -> None:
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        for p in profile.get("picks", []):
            if p["key"] == key:
                p["registered"] = done
                if not done and (p.get("submission") or {}).get("manual"):
                    p.pop("submission")       # an emailed registration stays on record, a hand-made one is undone
                    p.pop("outcome", None)
                    p.pop("outcome_at", None)
        _save(conn, request_id, profile, _finish_status(req, profile))


def set_status(request_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    with _connect() as conn:
        cur = conn.execute("UPDATE site_requests SET status = %s WHERE id = %s", (status, request_id))
        conn.commit()
        if cur.rowcount != 1:
            raise NotFound(request_id)


# ---------- Tracking: the organisers' replies, read over IMAP ----------

_UID_KEY = "requests_imap_uid"
_VALIDITY_KEY = "requests_imap_validity"
MAX_MESSAGE_BYTES = 2_000_000


def imap_configured() -> bool:
    return bool(config.REQUESTS_IMAP_HOST and config.REQUESTS_IMAP_USER)


def _message_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        text = part.get_content()
    except Exception:
        return ""
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _submissions(conn) -> tuple[dict, dict]:
    """Message-ID -> (request id, key) for every sent registration, and request ids by id."""
    by_message, by_id = {}, {}
    for r in conn.execute("SELECT id, profile FROM site_requests WHERE status IN ('confirmed', 'registered')"):
        by_id[r["id"]] = r
        for p in (r["profile"] or {}).get("picks", []):
            sub = p.get("submission") or {}
            if sub.get("message_id"):
                by_message[sub["message_id"].strip()] = (r["id"], p["key"])
    return by_message, by_id


def _find_submission(msg, by_message: dict) -> tuple[int, str] | None:
    refs = f"{msg.get('In-Reply-To', '')} {msg.get('References', '')}"
    for ref in re.findall(r"<[^<>\s]+>", refs):
        if ref in by_message:
            return by_message[ref]
    found = _TAG_RE.search(str(msg.get("Subject", "")))
    return _key_from_tag(found) if found else None


def _record_reply(conn, request_id: int, key: str, msg, text: str) -> bool:
    req = _load(conn, request_id)
    profile = dict(req["profile"] or {})
    pick = next((p for p in profile.get("picks", []) if p["key"] == key and p.get("submission")), None)
    message_id = str(msg.get("Message-ID", "")).strip()
    if pick is None or any(r.get("message_id") == message_id for r in pick.get("replies", [])):
        conn.rollback()
        return False
    sender = parseaddr(str(msg.get("From", "")))[1]
    if sender.lower() == (req["email"] or "").lower() or sender.lower() == config.REQUESTS_MAIL_FROM.lower():
        conn.rollback()
        return False                  # the visitor answering in the same thread, or our own copy
    try:
        verdict = ai.classify_registration_reply(event=pick["name"], subject=str(msg.get("Subject", "")), text=text)
    except Exception:
        log.exception("Classifying a reply for site request %s failed", request_id)
        verdict = {"outcome": "other", "summary": ""}
    pick.setdefault("replies", []).append({
        "message_id": message_id, "from": sender, "subject": str(msg.get("Subject", ""))[:300],
        "received_at": _now(), **verdict})
    if verdict["outcome"] != "other":
        pick["outcome"] = verdict["outcome"]
    _save(conn, request_id, profile)
    return True


def poll_replies(limit: int = 50) -> int:
    """Worker step: read new mail in the company inbox and attach organisers' replies to their registration.

    The mailbox is opened read-only and messages are fetched with BODY.PEEK, so nothing is marked as read.
    """
    if not (enabled() and imap_configured()):
        return 0
    try:
        conn = _connect()
    except filmdash.Unavailable:
        return 0
    found = 0
    with conn, imaplib.IMAP4_SSL(config.REQUESTS_IMAP_HOST, config.REQUESTS_IMAP_PORT,
                                 ssl_context=ssl.create_default_context(), timeout=30) as imap:
        imap.login(config.REQUESTS_IMAP_USER, config.REQUESTS_IMAP_PASSWORD)
        imap.select(config.REQUESTS_IMAP_FOLDER, readonly=True)
        validity = (imap.response("UIDVALIDITY")[1] or [b""])[0]
        validity = validity.decode() if isinstance(validity, bytes) else str(validity or "")
        last = settings.get(_UID_KEY) if settings.get(_VALIDITY_KEY) == validity else ""
        if not last:
            since = (date.today() - timedelta(days=CONFIRM_DAYS)).strftime("%d-%b-%Y")
            _, data = imap.uid("SEARCH", None, "SINCE", since)
        else:
            _, data = imap.uid("SEARCH", None, "UID", f"{int(last) + 1}:*")
        uids = [int(u) for u in (data[0] or b"").split() if not last or int(u) > int(last)][:limit]
        by_message, _ = _submissions(conn)
        for uid in uids:
            _, size_data = imap.uid("FETCH", str(uid), "(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (SUBJECT IN-REPLY-TO REFERENCES)])")
            head = next((part[1] for part in size_data if isinstance(part, tuple)), b"")
            size = re.search(rb"RFC822\.SIZE (\d+)", b" ".join(p[0] for p in size_data if isinstance(p, tuple)))
            msg = email.message_from_bytes(head, policy=email.policy.default)
            target = _find_submission(msg, by_message)
            if target and (not size or int(size.group(1)) <= MAX_MESSAGE_BYTES):
                _, full = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
                raw = next((part[1] for part in full if isinstance(part, tuple)), b"")
                msg = email.message_from_bytes(raw, policy=email.policy.default)
                try:
                    found += _record_reply(conn, *target, msg, _message_text(msg))
                except NotFound:
                    conn.rollback()
            settings.set(_UID_KEY, str(uid))
        if not last and not uids:
            settings.set(_UID_KEY, "0")
        settings.set(_VALIDITY_KEY, validity)
    return found


def update_mailto(req: dict, pick: dict, reply: dict) -> str:
    """A short note to the visitor about an organiser's reply, opened in the owner's mail app."""
    lang = i18n.normalize(req["lang"])
    body = "\n".join([_raw(lang, "rqmail.hello", name=req["name"]), "",
                      _raw(lang, "rqupd." + reply["outcome"], event=pick["name"]), "",
                      _raw(lang, "rqmail.closing"), config.REQUESTS_SIGNATURE or config.OWNER_NAME])
    return mailto(req["email"], _raw(lang, "rqupd.subject", event=pick["name"]), body)
