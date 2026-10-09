"""Ask Claude to extract funds and events from one snapshot, through the record_extraction tool."""
import json
import re
from datetime import date
from pathlib import Path

from pipeline import config

PROMPTS = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS / "extract-v1.txt").read_text()
TOOL = json.loads((PROMPTS / "record_extraction.json").read_text())

USER_TEMPLATE = """TODAY: {today_iso}
SOURCE_URL: {source_url}
SOURCE_TIER: {source_tier}
ORGANISATION_HINT: {organisation}
PAGE_LAST_MODIFIED: {page_modified}
EMAIL_SENT_AT: {email_sent_at}
KNOWN_RECORDS: {known_records}

<document>
{clean_text}
</document>

Extract every fund and event this document describes. If an item matches one in
KNOWN_RECORDS, reuse its slug."""

# The page is untrusted text: a look-alike tag inside it must not close the wrapper.
_DOC_TAG = re.compile(r"<(/?)document\b", re.I)


def build_user_message(*, clean_text: str, source_url: str, source_tier: str, organisation: str | None = None,
                       page_modified: str | None = None, email_sent_at: str | None = None,
                       known_records: list[dict] | None = None, today: date | None = None) -> str:
    return USER_TEMPLATE.format(
        today_iso=(today or date.today()).isoformat(),
        source_url=source_url,
        source_tier=source_tier,
        organisation=organisation or "",
        page_modified=page_modified or "",
        email_sent_at=email_sent_at or "",
        known_records=json.dumps(known_records or [], ensure_ascii=False),
        clean_text=_DOC_TAG.sub(r"<\1_document", clean_text[: config.MAX_DOCUMENT_CHARS]),
    )


def make_client():
    import anthropic
    return anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY", config.ANTHROPIC_API_KEY))


def call_claude(client, user_message: str, model: str | None = None) -> tuple[dict, dict]:
    """Returns (tool input, usage). Raises if the model did not call the tool."""
    response = client.messages.create(
        model=model or config.EXTRACT_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": TOOL["name"]},
        messages=[{"role": "user", "content": user_message}],
    )
    usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL["name"]:
            return dict(block.input), usage
    raise RuntimeError(f"model did not call {TOOL['name']} (stop_reason={response.stop_reason})")
