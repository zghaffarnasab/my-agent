import os
import sys
import tempfile

# Fake settings, set BEFORE the app is imported. No real keys, no real Gmail/Google/Anthropic calls.
_tmp = tempfile.mkdtemp()
os.environ.update({
    "SECRET_KEY": "test-secret",
    "DASHBOARD_PASSWORD": "test-password",
    "GOOGLE_CLIENT_ID": "x",
    "GOOGLE_CLIENT_SECRET": "x",
    "ANTHROPIC_API_KEY": "x",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "BASE_URL": "http://localhost:8000",
    "DEFAULT_LANGUAGE": "en",
    "TIMEZONE": "Europe/London",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    from app.db import init_db
    init_db()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from app import settings
    settings._cache.clear()
    yield
    settings._cache.clear()
