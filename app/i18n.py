"""Tiny translation helper: flat JSON files (app/locales/<lang>.json) and a t() function."""
import json
import os

SUPPORTED = ("en", "fa")
DIRECTION = {"en": "ltr", "fa": "rtl"}
LANGUAGE_NAMES = {"en": "English", "fa": "Persian (Farsi)"}   # for AI prompts
_DIR = os.path.join(os.path.dirname(__file__), "locales")
_cache: dict[str, dict[str, str]] = {}

# First Strong Isolate / Pop Directional Isolate: keeps inserted values (times, emails, names)
# from reordering the surrounding sentence. Digits-only values stay left-to-right.
_FSI, _PDI = "⁨", "⁩"


def messages(lang: str) -> dict[str, str]:
    if lang not in _cache:
        with open(os.path.join(_DIR, f"{lang}.json"), encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


def translate(lang: str, key: str, **params) -> str:
    text = messages(lang).get(key)
    if text is None:
        text = messages("en").get(key, key)
    if params:
        text = text.format(**{k: f"{_FSI}{v}{_PDI}" for k, v in params.items()})
    return text


def normalize(lang: str | None, default: str = "en") -> str:
    return lang if lang in SUPPORTED else default
