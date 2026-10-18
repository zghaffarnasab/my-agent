"""Requests sent through the website form, matched to published funds and events.

The website (a separate app) inserts rows into `site_requests` in the same Postgres as the pipeline.
This module only reads the pipeline tables, and on `site_requests` it only changes `status` and the
`profile` JSON (suggestions, the owner's choices, the offer email). Nothing reaches the visitor or an
organiser without the owner pressing a button, and registration on other sites is always done by hand.
"""
import logging
import smtplib
import ssl
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from urllib.parse import quote

import psycopg
from psycopg.types.json import Jsonb

from app import ai, config, filmdash, i18n

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
UK_NAMES = {"uk", "u.k.", "united kingdom", "great britain", "britain", "gb", "england", "scotland", "wales",
            "northern ireland", "london",
            # The same in Persian (data, not UI text; escaped so the no-hardcoded-Persian test stays simple).
            "\u0628\u0631\u06cc\u062a\u0627\u0646\u06cc\u0627", "\u0627\u0646\u06af\u0644\u06cc\u0633", "\u0627\u0646\u06af\u0644\u0633\u062a\u0627\u0646", "\u0627\u0633\u06a9\u0627\u062a\u0644\u0646\u062f", "\u0648\u0644\u0632"}

MAX_CANDIDATES = 12       # sent to the AI to choose from
MAX_PICKS = 5


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
       f.stages::text[] AS stages, f.forms, f.genres, f.summary, f.amount_min, f.amount_max, f.amount_currency,
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
       '{}'::text[] AS stages, '{}'::text[] AS forms, e.genres, e.summary, NULL::numeric AS amount_min,
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


def _is_uk(country: str | None) -> bool:
    return (country or "").strip().lower() in UK_NAMES


def _score(rec: dict, req: dict, today: date) -> int | None:
    """Rule-based fit. None = clearly not a fit (dropped before the AI sees it)."""
    score = 0
    in_uk = _is_uk(req.get("country"))
    if rec["uk_eligible"] == "no" and in_uk:
        return None
    if rec["uk_eligible"] == "yes" and in_uk:
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


def _how_to_register(lang: str, pick: dict) -> str:
    if pick["platform"] == "email" or pick["apply_email"]:
        return _raw(lang, "rqmail.how_email")
    if pick["platform"] == "filmfreeway":
        return _raw(lang, "rqmail.how_filmfreeway")
    return _raw(lang, "rqmail.how_site")


def draft_offer(req: dict, picks: list[dict], note: str) -> dict:
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
            when = f"\u200e{p['next_date']}\u200e" if i18n.DIRECTION[lang] == "rtl" else p["next_date"]
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
    lines += [_raw(lang, "rqmail.next_step"), "", _raw(lang, "rqmail.closing"),
              config.REQUESTS_SIGNATURE or config.OWNER_NAME]
    return {"subject": _raw(lang, "rqmail.subject"), "body": "\n".join(lines).strip()}


def choose(request_id: int, keys: list[str], note: str) -> dict:
    """Keep only the options the owner ticked and write the offer email draft."""
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        picks = profile.get("picks", [])
        for p in picks:
            p["chosen"] = p["key"] in keys
        profile["note"] = note.strip()[:2000]
        chosen = [p for p in picks if p["chosen"]]
        profile["offer"] = draft_offer(req, chosen, profile["note"]) if chosen else None
        _save(conn, request_id, profile)
    return profile


def mail_configured() -> bool:
    return bool(config.REQUESTS_MAIL_HOST and config.REQUESTS_MAIL_FROM)


def _send_mail(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = formataddr((config.REQUESTS_SIGNATURE or "", config.REQUESTS_MAIL_FROM))
    msg["To"] = to
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


def mailto(to: str, subject: str, body: str) -> str:
    return f"mailto:{quote(to, safe='@')}?subject={quote(subject)}&body={quote(body)}"


def organiser_address(pick: dict) -> str:
    if pick.get("apply_email"):
        return pick["apply_email"]
    url = pick.get("url") or ""
    return url[len("mailto:"):].split("?")[0] if url.lower().startswith("mailto:") else ""


def registration_mailto(req: dict, pick: dict) -> str:
    """A ready email to the organiser for options that take registrations by email (sent by the owner)."""
    to = organiser_address(pick)
    if not to:
        return ""
    rows = [("name", req["name"]), ("email", req["email"]), ("country", req["country"]),
            ("film", req["film_title"]), ("film_type", req["film_type"]), ("stage", req["stage"])]
    facts = "\n".join(f"{_raw('en', 'rqreg.' + k)}: {v}" for k, v in rows if v)
    body = _raw("en", "rqreg.body", event=pick["name"], facts=facts, email=req["email"])
    return mailto(to, _raw("en", "rqreg.subject", event=pick["name"], name=req["name"]), body)


def set_registered(request_id: int, key: str, done: bool) -> None:
    with _connect() as conn:
        req = _load(conn, request_id)
        profile = dict(req["profile"] or {})
        for p in profile.get("picks", []):
            if p["key"] == key:
                p["registered"] = done
        chosen = [p for p in profile.get("picks", []) if p.get("chosen")]
        status = req["status"]
        if chosen and all(p["registered"] for p in chosen):
            status = "registered"
        elif status == "registered":
            status = "confirmed"
        _save(conn, request_id, profile, status)


def set_status(request_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    with _connect() as conn:
        cur = conn.execute("UPDATE site_requests SET status = %s WHERE id = %s", (status, request_id))
        conn.commit()
        if cur.rowcount != 1:
            raise NotFound(request_id)
