"""English is the default interface language. Order: cookie -> Settings page -> DEFAULT_LANGUAGE (default "en")."""
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import config, main, settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _no_saved_language():
    settings.set("language", "")
    yield
    settings.set("language", "")


def _lang_of(html: str) -> str:
    return "fa" if '<html lang="fa" dir="rtl">' in html else "en" if '<html lang="en" dir="ltr">' in html else "?"


def test_the_built_in_default_is_english():
    env = {k: v for k, v in os.environ.items() if k != "DEFAULT_LANGUAGE"} | {"PYTHONPATH": ROOT}
    out = subprocess.run([sys.executable, "-c", "import app.config as c; print(c.DEFAULT_LANGUAGE)"],
                         env=env, cwd=os.path.join(ROOT, "tests"), capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "en"


def test_env_example_says_default_language_en():
    lines = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read().splitlines()
    assert "DEFAULT_LANGUAGE=en" in lines


def test_a_new_visitor_gets_english_ltr_everywhere():
    c = TestClient(main.app)
    login = c.get("/login").text
    assert _lang_of(login) == "en" and "Log in" in login and "Reply queue" in login
    assert c.post("/login", data={"password": "test-password"}, follow_redirects=False).status_code == 303
    for path in ("/", "/settings", "/changelog"):
        assert _lang_of(c.get(path).text) == "en", path


def test_order_is_cookie_then_settings_then_env(monkeypatch):
    c = TestClient(main.app)
    assert _lang_of(c.get("/login").text) == "en"                       # nothing set: English

    monkeypatch.setattr(config, "DEFAULT_LANGUAGE", "fa")               # .env says Persian
    assert _lang_of(c.get("/login").text) == "fa"

    settings.set("language", "en")                                      # the Settings page beats .env
    settings._cache.clear()
    assert _lang_of(c.get("/login").text) == "en"

    settings.set("language", "fa")
    settings._cache.clear()
    c.cookies.set("lang", "en")                                         # the visitor's own choice beats both
    assert _lang_of(c.get("/login").text) == "en"
    c.cookies.set("lang", "fa")
    settings.set("language", "en")
    settings._cache.clear()
    assert _lang_of(c.get("/login").text) == "fa"


def test_invalid_values_fall_back_to_english(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_LANGUAGE", "klingon")
    c = TestClient(main.app)
    c.cookies.set("lang", "de")
    assert _lang_of(c.get("/login").text) == "en"


def test_the_language_switch_still_remembers_the_choice():
    c = TestClient(main.app)
    c.post("/language", data={"lang": "fa", "next": "/login"})
    assert _lang_of(c.get("/login").text) == "fa"
    c.post("/language", data={"lang": "en", "next": "/login"})
    assert _lang_of(c.get("/login").text) == "en"
