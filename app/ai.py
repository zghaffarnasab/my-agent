import anthropic

from app import config

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
