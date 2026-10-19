"""Visitor country text -> ISO code, and open_to coverage (no DB needed)."""
from app import countries


def test_code_reads_english_persian_and_codes():
    assert countries.code("Germany") == "DE"
    assert countries.code("  United Kingdom ") == "GB"
    assert countries.code("London, UK") == "GB"
    assert countries.code("\u0622\u0644\u0645\u0627\u0646") == "DE"     # Persian for Germany
    assert countries.code("uk") == "GB" and countries.code("fr") == "FR"
    assert countries.code("Atlantis") is None and countries.code("") is None


def test_covers_groups():
    assert countries.covers(["MEDIA"], "DE") is True
    assert countries.covers(["MEDIA"], "GB") is False       # the UK left Creative Europe MEDIA
    assert countries.covers(["EU"], "NO") is False and countries.covers(["EEA"], "NO") is True
    assert countries.covers(["EUROPE"], "GB") is True
    assert countries.covers(["WORLD"], "IR") is True
    assert countries.covers(["DK", "SE"], "SE") is True and countries.covers(["DK"], "DE") is False
    assert countries.covers([], "DE") is None and countries.covers(["DK"], None) is None
