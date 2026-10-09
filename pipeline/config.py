import os

from dotenv import load_dotenv

load_dotenv()

# Postgres connection string, e.g. postgresql://filmdash:secret@db:5432/filmdash
DATABASE_URL = os.getenv("PIPELINE_DATABASE_URL", "")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "claude-sonnet-5-5")
PROMPT_VERSION = "extract-v1"

# Identifies the bot to the sites it reads.
USER_AGENT = os.getenv("PIPELINE_USER_AGENT", "filmdash-pipeline/0.1 (+change detection of public funding pages)")
FETCH_TIMEOUT_SECONDS = float(os.getenv("FETCH_TIMEOUT_SECONDS", "30"))
# Very long pages are cut before they are sent to Claude (characters of clean text).
MAX_DOCUMENT_CHARS = int(os.getenv("MAX_DOCUMENT_CHARS", "60000"))


def require(name: str, value: str) -> str:
    if not value:
        raise SystemExit(f"Environment variable {name} is required (see pipeline/.env.example)")
    return value
