"""Pipeline validation rules: quotes must be verbatim, values must be inside their quotes (no DB needed)."""
from datetime import date

from pipeline import validate

PAGE = ("Round 2 opens on 9 November 2026 at 13:00 and closes on 21 December 2026 at 13:00 (UK time). "
        "Grants of between £25,000 and £40,000. The lead director must be resident in the UK. "
        "Decisions will be announced in Spring 2027. Entry fee: £40 early, £58 late. "
        "The deadline is 05/01/2027. This fund is open to “UK-based” filmmakers.")


def _fund(**over):
    item = {
        "kind": "fund", "slug": "Example Dev Fund", "name": "Example Dev Fund", "uk_eligible": "unknown",
        "dates": [], "evidence": [], "confidence": 0.9,
    }
    item.update(over)
    return item


def _run(item, tier="official", page=PAGE):
    return validate.validate_extraction({"items": [item], "notes": ""}, page, tier)


def test_normalise_ignores_nbsp_curly_quotes_and_line_breaks():
    doc = validate.normalise(PAGE)
    assert validate.quote_found("opens on 9 November 2026", doc)
    assert validate.quote_found('open to "UK-based"\nfilmmakers', doc)
    assert not validate.quote_found("opens on 10 November 2026", doc)


def test_date_in_quote_needs_day_month_and_year():
    assert validate.date_in_quote(date(2026, 12, 21), "closes on 21 December 2026 at 13:00")
    assert validate.date_in_quote(date(2026, 12, 21), "closes on 21st Dec 2026")
    assert validate.date_in_quote(date(2027, 1, 5), "The deadline is 05/01/2027.")
    assert not validate.date_in_quote(date(2026, 12, 21), "closes on 21 December")        # no year
    assert not validate.date_in_quote(date(2026, 12, 22), "closes on 21 December 2026")   # wrong day


def test_amounts_in_quote():
    assert validate.amounts_in("between £25,000 and £40,000") == {25000, 40000}
    assert 1_000_000 in validate.amounts_in("up to £1m")
    assert 5000 in validate.amounts_in("£5k to £25k")


def test_good_dates_are_kept_and_slug_cleaned():
    res = _run(_fund(dates=[
        {"kind": "opens", "label": "Round 2 opens", "status": "confirmed", "date_value": "2026-11-09",
         "time_value": "13:00", "tz": "Europe/London", "source_quote": "Round 2 opens on 9 November 2026 at 13:00"},
        {"kind": "results", "status": "expected", "approx_text": "Spring 2027",
         "approx_from": "2027-03-01", "approx_to": "2027-05-31",
         "source_quote": "Decisions will be announced in Spring 2027."},
    ]))
    item = res.items[0]
    assert item["slug"] == "example-dev-fund"
    assert [d["kind"] for d in item["dates"]] == ["opens", "results"]
    assert item["dates"][0]["date_value"] == date(2026, 11, 9)
    assert res.rejected == []


def test_invented_or_mismatched_dates_are_dropped():
    res = _run(_fund(dates=[
        # quote not in the page
        {"kind": "deadline", "status": "confirmed", "date_value": "2027-03-01", "source_quote": "closes 1 March 2027"},
        # quote is real but the date is not in it
        {"kind": "deadline", "status": "confirmed", "date_value": "2026-12-22",
         "source_quote": "closes on 21 December 2026 at 13:00"},
        # expected must not carry a date
        {"kind": "results", "status": "expected", "date_value": "2027-04-01", "approx_text": "Spring 2027",
         "source_quote": "Decisions will be announced in Spring 2027."},
        # confirmed needs a date
        {"kind": "deadline", "status": "confirmed", "source_quote": "closes on 21 December 2026"},
    ]))
    assert res.items[0]["dates"] == []
    reasons = [r["reason"] for r in res.rejected]
    assert reasons == ["quote not found in page", "date not found in its quote",
                       "expected date must not have date_value", "confirmed date without date_value"]


def test_non_official_source_cannot_confirm():
    res = _run(_fund(dates=[{"kind": "deadline", "status": "confirmed", "date_value": "2026-12-21",
                             "source_quote": "closes on 21 December 2026"}],
                     amount_max=40000, amount_status="confirmed",
                     evidence=[{"field": "amount_max", "value": "40000", "source_quote": "and £40,000"}]),
               tier="aggregator")
    item = res.items[0]
    assert item["dates"][0]["status"] == "unverified"
    assert item["amount_status"] == "unverified"


def test_amounts_need_a_matching_evidence_quote():
    res = _run(_fund(amount_min=25000, amount_max=50000, amount_currency="gbp",
                     evidence=[{"field": "amount", "value": "£25,000-£40,000",
                                "source_quote": "Grants of between £25,000 and £40,000"}]))
    item = res.items[0]
    assert item["amount_min"] == 25000 and item["amount_max"] is None
    assert item["amount_currency"] == "GBP"
    assert [r["what"] for r in res.rejected] == ["amount_max"]


def test_eligibility_fields_need_evidence():
    res = _run(_fund(uk_eligible="yes", residency_rule="director resident in the UK",
                     nationality_rule="British passport holders"
                     , evidence=[
                         {"field": "uk_eligible", "value": "yes",
                          "source_quote": "The lead director must be resident in the UK."},
                         {"field": "residency_rule", "value": "UK resident director",
                          "source_quote": "The lead director must be resident in the UK."},
                     ]))
    item = res.items[0]
    assert item["uk_eligible"] == "yes"
    assert item["residency_rule"] == "director resident in the UK"
    assert item["nationality_rule"] is None
    res = _run(_fund(uk_eligible="no"))
    assert res.items[0]["uk_eligible"] == "unknown"


def test_event_fees_and_platform():
    res = _run({"kind": "event", "slug": "x-fest-2027", "name": "X Fest", "uk_eligible": "unknown",
                "event_type": "festival", "edition_year": 2027, "fee_min": 40, "fee_max": 58,
                "fee_currency": "GBP", "submit_platform": "filmfreeway", "confidence": 2,
                "dates": [], "evidence": [{"field": "fee", "value": "£40-£58",
                                           "source_quote": "Entry fee: £40 early, £58 late."}]})
    item = res.items[0]
    assert (item["fee_min"], item["fee_max"]) == (40, 58)
    assert item["submit_platform"] == "unknown"     # no evidence for the platform
    assert item["confidence"] == 1.0


def test_item_without_name_is_rejected():
    res = _run({"kind": "fund", "slug": "", "name": "", "dates": [], "evidence": []})
    assert res.items == [] and res.rejected[0]["what"] == "item"


def test_html_entities_in_names_are_decoded():
    res = _run(_fund(name="Film &amp; TV Award", slug="film-tv-award"))
    assert res.items[0]["name"] == "Film & TV Award"
