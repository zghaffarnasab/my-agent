import json
import os
import re

from app import i18n
from app.version import CHANGELOG, VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _files(folder, ext):
    for base, _, names in os.walk(os.path.join(ROOT, folder)):
        for n in names:
            if n.endswith(ext):
                yield os.path.join(base, n)


def test_both_languages_have_the_same_keys():
    en, fa = i18n.messages("en"), i18n.messages("fa")
    assert set(en) == set(fa)


def test_placeholders_match_between_languages():
    en, fa = i18n.messages("en"), i18n.messages("fa")
    for key in en:
        assert set(PLACEHOLDER.findall(en[key])) == set(PLACEHOLDER.findall(fa[key])), key


def test_every_key_used_in_code_and_templates_exists():
    known = set(i18n.messages("en"))
    used = set()
    for path in list(_files("app/templates", ".html")) + list(_files("app", ".py")):
        text = open(path, encoding="utf-8").read()
        used |= set(re.findall(r"""\bt\(\s*["']([a-z_]+\.[a-z_0-9.]+)["']""", text))
        used |= set(re.findall(r"""flash\(request,\s*["']([a-z_]+\.[a-z_0-9.]+)["']""", text))
        used |= set(re.findall(r"""["'](flash\.[a-z_]+)["']""", text))
    assert used, "no keys found; the regex is broken"
    assert used - known == set()


def test_dynamic_key_families_exist():
    known = set(i18n.messages("en"))
    for status in ("pending", "failed", "sent", "rejected", "sending", "info", "done"):
        assert f"status.{status}" in known
    for i in range(7):
        assert f"weekday.{i}" in known
    for tab in ("reply", "events", "other", "sent", "rejected"):
        assert f"tab.{tab}" in known
    from app.validation import CATEGORIES, WARNING_CODES
    for category in CATEGORIES:
        assert f"category.{category}" in known
    for code in WARNING_CODES:
        assert f"warning.{code}" in known


def test_no_persian_text_hardcoded_in_python_or_templates():
    persian = re.compile(r"[؀-ۿ]")
    allowed = {"version.py"}   # the changelog is bilingual data
    for path in list(_files("app", ".py")) + list(_files("app/templates", ".html")):
        if os.path.basename(path) in allowed:
            continue
        for line in open(path, encoding="utf-8"):
            line = line.replace("فارسی", "")   # the language switcher label is shown in its own language
            assert not persian.search(line), f"{path}: {line.strip()}"


def test_changelog_is_bilingual_and_current():
    assert CHANGELOG[0]["version"] == VERSION
    for rel in CHANGELOG:
        for lang in i18n.SUPPORTED:
            assert rel["title"][lang].strip()
            assert rel["changes"][lang]
        assert len(rel["changes"]["en"]) == len(rel["changes"]["fa"])


def test_translate_isolates_values_and_falls_back_to_key():
    out = i18n.translate("en", "flash.events_found", n=3)
    assert out.replace("⁨", "").replace("⁩", "") == "3 event(s) found."
    assert i18n.translate("en", "no.such.key") == "no.such.key"
