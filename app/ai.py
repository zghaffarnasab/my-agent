import anthropic

from app import config, i18n, settings

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are an email assistant that drafts replies on behalf of {owner}.

Rules:
- Write ONLY the body of the reply. No subject line, no explanations, no notes to the user.
- Reply in the same language the sender used (for example Persian -> Persian, English -> English, German -> German).
- Style: {style}
- Answer what the sender actually asked. Do not invent facts, dates, prices, promises or commitments.
  If information is missing, write a placeholder in square brackets, e.g. [confirm the meeting time],
  so the owner can fill it in before sending.
- Do not include the quoted original email.
{signature_rule}"""


def _system_prompt() -> str:
    owner = config.OWNER_NAME or "the mailbox owner"
    if config.EMAIL_SIGNATURE:
        signature_rule = f"- End the email with exactly this signature:\n{config.EMAIL_SIGNATURE}"
    else:
        signature_rule = f"- End with a short closing{' and the name ' + config.OWNER_NAME if config.OWNER_NAME else ''}."
    return SYSTEM_PROMPT.format(owner=owner, style=config.REPLY_STYLE, signature_rule=signature_rule)


def draft_reply(*, from_addr: str, subject: str, body: str, thread_context: str = "",
                previous_draft: str = "", instruction: str = "") -> str:
    parts = []
    if thread_context:
        parts.append(f"<earlier_messages_in_thread>\n{thread_context}\n</earlier_messages_in_thread>")
    parts.append(
        f"<email_to_reply_to>\nFrom: {from_addr}\nSubject: {subject}\n\n{body}\n</email_to_reply_to>"
    )
    if previous_draft and instruction:
        parts.append(f"<previous_draft>\n{previous_draft}\n</previous_draft>")
        parts.append(f"Rewrite the draft following this instruction from the owner: {instruction}")
    elif instruction:
        parts.append(f"Extra instruction from the owner: {instruction}")
    else:
        parts.append("Draft the reply.")

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        system=_system_prompt(),
        messages=[{"role": "user", "content": "\n\n".join(parts)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip()


# ---------- Event extraction ----------

EXTRACT_PROMPT = """You find meetings, appointments, calls and events with a concrete date in an email.

Context:
- The email was {when} (reference time, in the owner's time zone {tz}). Today's weekday then: {weekday}.
- The owner's time zone is {tz}.
- This email was {direction}.

Rules:
- Only include events that are being proposed, agreed or announced with a specific day.
  Ignore vague mentions ("let's meet sometime"), past events and pure deadlines.
- Dates like 13.09 or 13/09 are day.month (European style) unless the text clearly uses US style.
  If a date could be read both ways (e.g. 03.04), choose day.month and add the warning date_format_ambiguous.
- If the year is missing, use the next occurrence on or after the reference date and add the warning year_missing.
- Resolve relative dates ("next Tuesday", "tomorrow") against the reference date.
- Time zone: if the place or text implies a different time zone than the owner's
  (e.g. a meeting in Berkeley, California), use that IANA zone (e.g. America/Los_Angeles)
  and add the warning timezone_guessed. Online meetings use the owner's zone unless stated otherwise.
- If no end time or duration is given, leave end_time empty.
- title: short, e.g. "Meeting with Sara (Acme Films)". Same language as the email.
- description: one short sentence, written in {language}.
- "warnings": a list of codes, chosen ONLY from this fixed list, for things the owner should double-check:
    date_format_ambiguous (e.g. 03.04 could be 3 April or 4 March),
    year_missing (the year was not given and you guessed it),
    timezone_guessed (the time zone was inferred from a place),
    conflicting_times (the text gives different dates or times for the same event),
    location_hidden (the exact location is not shown, e.g. "register to see location"),
    am_pm_unclear, multi_day_unclear.
  Use an empty list when nothing is uncertain. NEVER write free text in "warnings".
  Do not add warnings about names, signatures, or whether the meeting is confirmed.

Respond with ONLY a JSON object, no markdown, in exactly this shape:
{{"events": [{{"title": "", "date": "YYYY-MM-DD", "start_time": "HH:MM or empty", "end_time": "HH:MM or empty",
  "timezone": "IANA zone", "location": "", "description": "one short sentence", "warnings": []}}]}}
If there are no events, respond with {{"events": []}}"""


def extract_events(*, text: str, subject: str, from_addr: str, reference, outgoing: bool) -> list[dict]:
    """Return a list of event dicts found in an email. `reference` is an aware datetime."""
    import json
    from zoneinfo import ZoneInfo

    local = reference.astimezone(ZoneInfo(settings.get_timezone()))
    system = EXTRACT_PROMPT.format(
        when=("sent" if outgoing else "received") + " on " + local.strftime("%Y-%m-%d %H:%M"),
        weekday=local.strftime("%A"),
        tz=settings.get_timezone(),
        language=i18n.LANGUAGE_NAMES[settings.get_language()],
        direction="written BY the owner as a reply (events the owner proposes or confirms)"
        if outgoing else "received BY the owner",
    )
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1200,
        system=system,
        messages=[{"role": "user", "content": f"From: {from_addr}\nSubject: {subject}\n\n{text[:12000]}"}],
    )
    raw = "".join(b.text for b in response.content if b.type == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start != -1 and end > start else {"events": []}
    return [e for e in data.get("events", []) if isinstance(e, dict)]
