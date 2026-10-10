"""Code-side checks on Claude's extraction (prompt section 5). The prompt asks; this module enforces.

Every date, amount and filled eligibility field must carry a quote that is found verbatim in the
page text, and the value must appear inside its quote. Anything that fails is dropped and logged
in extraction_runs.rejected_items; nothing is "fixed" by guessing.
"""
import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

DATE_KINDS = {"opens", "deadline", "deadline_early", "deadline_regular", "deadline_late", "deadline_extended",
              "event_start", "event_end", "results", "closure_start", "closure_end", "other"}
DATE_STATUSES = {"confirmed", "expected", "unverified", "conflict", "closed"}
EVENT_TYPES = {"festival", "market", "lab", "workshop", "pitch", "award", "talent_programme", "other"}
FORMATS = {"in_person", "online", "hybrid", "unknown"}
PLATFORMS = {"filmfreeway", "own_site", "email", "bfi_portal", "other", "unknown"}
STAGES = {"development", "production", "post_production", "distribution", "festival_travel", "talent", "other"}
DEADLINE_MODES = {"fixed", "rolling", "rounds", "unknown"}
UK_ELIGIBLE = {"yes", "no", "partial", "unknown"}
QUALIFYING_BODIES = {"BAFTA", "BIFA", "Oscars", "BAFTA Cymru", "Other"}
# Text fields that are cleared unless an evidence entry with a found quote backs them.
FIELDS_NEEDING_EVIDENCE = ("residency_rule", "nationality_rule", "other_eligibility")

MONTHS = {
    1: ("january", "jan"), 2: ("february", "feb"), 3: ("march", "mar"), 4: ("april", "apr"),
    5: ("may",), 6: ("june", "jun"), 7: ("july", "jul"), 8: ("august", "aug"),
    9: ("september", "sept", "sep"), 10: ("october", "oct"), 11: ("november", "nov"), 12: ("december", "dec"),
}

_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
                         "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
                         "​": None, "‌": None, "‍": None, "﻿": None})


def normalise(text: str) -> str:
    """Same text, but curly quotes, dashes, non-breaking spaces and line breaks don't matter."""
    text = unicodedata.normalize("NFKC", text or "").translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str | None, norm_doc: str) -> bool:
    q = normalise(quote or "").strip('"')
    return len(q) >= 3 and q in norm_doc


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def date_in_quote(value: date, quote: str) -> bool:
    """Day, month and year of `value` all appear in the quote (as words or as a numeric date)."""
    q = normalise(quote).lower()
    for a, b, c in re.findall(r"(?<!\d)(\d{1,4})[/.\-](\d{1,2})[/.\-](\d{2,4})(?!\d)", q):
        a, b, c = int(a), int(b), int(c)
        for y, m, d in ((c, b, a), (a, b, c)):          # dd/mm/yyyy or yyyy-mm-dd
            if y < 100:
                y += 2000
            if (y, m, d) == (value.year, value.month, value.day):
                return True
    day = re.search(rf"(?<!\d)0?{value.day}(?:st|nd|rd|th)?(?!\d)", q)
    month = any(re.search(rf"\b{name}\b", q) for name in MONTHS[value.month])
    return bool(day and month and str(value.year) in q)


_AMOUNT = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(k|m|bn|thousand|million|billion)?(?![a-z])", re.I)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9}


def amounts_in(quote: str) -> set[float]:
    found = set()
    for num, suffix in _AMOUNT.findall(normalise(quote)):
        found.add(round(float(num.replace(",", "")) * _MULT.get(suffix.lower(), 1), 2))
    return found


def _amount_backed(value: float, quotes: list[str]) -> bool:
    return any(abs(v - float(value)) < 0.01 for q in quotes for v in amounts_in(q))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalise(text).lower()).strip("-")[:120]


def _enum(value, allowed, default=None):
    return value if value in allowed else default


def _url(value):
    return value if isinstance(value, str) and re.match(r"https?://", value) else None


def _currency(value):
    return value.upper() if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value) else None


def _number(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Result:
    items: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)


def validate_extraction(output: dict, clean_text: str, source_tier: str) -> Result:
    doc = normalise(clean_text)
    res = Result()
    for raw in (output or {}).get("items") or []:
        item = _validate_item(raw, doc, source_tier, res.rejected)
        if item:
            res.items.append(item)
    return res


def _validate_item(raw: dict, doc: str, tier: str, rejected: list[dict]) -> dict | None:
    for key in ("name", "strand", "organisation", "summary"):   # the model sometimes copies "&amp;" from HTML
        if isinstance(raw.get(key), str):
            raw[key] = html.unescape(raw[key])
    name = (raw.get("name") or "").strip()
    slug = slugify(raw.get("slug") or name)

    def reject(what, reason, detail=None):
        rejected.append({"item": slug or name, "what": what, "reason": reason, "detail": detail})

    if raw.get("kind") not in ("fund", "event") or not name or not slug:
        reject("item", "missing kind or name", raw.get("name"))
        return None

    item = {
        "kind": raw["kind"], "slug": slug, "name": name[:300],
        "organisation": (raw.get("organisation") or "").strip() or None,
        "strand": (raw.get("strand") or "").strip() or None,
        "summary": (raw.get("summary") or "")[:300] or None,
        "confidence": min(max(_number(raw.get("confidence")) or 0.5, 0.0), 1.0),
    }

    # Evidence first: other checks rely on its (verified) quotes.
    evidence = []
    for ev in raw.get("evidence") or []:
        if not ev.get("field") or not quote_found(ev.get("source_quote"), doc):
            reject(f"evidence:{ev.get('field')}", "quote not found in page", ev.get("source_quote"))
            continue
        evidence.append({"field": str(ev["field"])[:80], "value": str(ev.get("value") or "")[:1000],
                         "source_quote": ev["source_quote"].strip()})
    item["evidence"] = evidence

    def quotes_for(prefix):
        return [e["source_quote"] for e in evidence if e["field"].startswith(prefix)]

    def backed_amount(fieldname, prefix):
        value = _number(raw.get(fieldname))
        if value is None:
            return None
        if not _amount_backed(value, quotes_for(prefix)):
            reject(fieldname, "amount not found in its quote", value)
            return None
        return value

    # Dates
    dates = []
    for d in raw.get("dates") or []:
        what = f"date:{d.get('kind')}:{d.get('label') or ''}"
        status = d.get("status")
        if d.get("kind") not in DATE_KINDS or status not in DATE_STATUSES:
            reject(what, "unknown date kind or status", status)
            continue
        if not quote_found(d.get("source_quote"), doc):
            reject(what, "quote not found in page", d.get("source_quote"))
            continue
        value = _parse_date(d.get("date_value"))
        if d.get("date_value") and value is None:
            reject(what, "date_value is not YYYY-MM-DD", d.get("date_value"))
            continue
        if status == "confirmed" and tier != "official":
            status = "unverified"
        approx_from, approx_to = _parse_date(d.get("approx_from")), _parse_date(d.get("approx_to"))
        if approx_from and approx_to and approx_from > approx_to:
            approx_from = approx_to = None
        approx_text = (d.get("approx_text") or "").strip() or None
        if status == "expected" and value:
            reject(what, "expected date must not have date_value", d.get("date_value"))
            continue
        if status == "expected" and not (approx_text or approx_from):
            reject(what, "expected date without approx_text", None)
            continue
        if status in ("confirmed", "closed") and not value:
            reject(what, f"{status} date without date_value", None)
            continue
        if value and not date_in_quote(value, d["source_quote"]):
            reject(what, "date not found in its quote", d.get("date_value"))
            continue
        time_value = d.get("time_value") if re.fullmatch(r"\d{2}:\d{2}", str(d.get("time_value") or "")) else None
        dates.append({
            "kind": d["kind"], "label": (d.get("label") or "").strip() or None, "status": status,
            "date_value": value, "time_value": time_value, "tz": (d.get("tz") or None),
            "approx_text": approx_text, "approx_from": approx_from, "approx_to": approx_to,
            "source_quote": d["source_quote"].strip(),
        })
    item["dates"] = dates

    # UK eligibility must be backed by a quote, and "no" needs a reason.
    uk = _enum(raw.get("uk_eligible"), UK_ELIGIBLE, "unknown")
    uk_quotes = quotes_for("uk_")
    reason = (raw.get("uk_not_eligible_reason") or "").strip() or None
    if uk != "unknown" and not uk_quotes:
        reject("uk_eligible", "no evidence quote", uk)
        uk = "unknown"
    if uk == "no" and not reason:
        reason = uk_quotes[0]
    item["uk_eligible"] = uk
    item["uk_not_eligible_reason"] = reason if uk == "no" else None

    for name_ in FIELDS_NEEDING_EVIDENCE:
        value = (raw.get(name_) or "").strip() or None
        if value and not quotes_for(name_):
            reject(name_, "no evidence quote", value)
            value = None
        item[name_] = value

    if item["kind"] == "fund":
        amin, amax = backed_amount("amount_min", "amount"), backed_amount("amount_max", "amount")
        if amin is not None and amax is not None and amin > amax:
            reject("amount", "amount_min > amount_max", [amin, amax])
            amin = amax = None
        amount_status = _enum(raw.get("amount_status"), {"confirmed", "unverified", "conflict"}, "unverified")
        if amount_status == "confirmed" and tier != "official":
            amount_status = "unverified"
        item.update({
            "stages": [s for s in raw.get("stages") or [] if s in STAGES],
            "forms": [str(f)[:40] for f in raw.get("forms") or []],
            "genres": [str(g)[:40] for g in raw.get("genres") or []],
            "amount_min": amin, "amount_max": amax,
            "amount_currency": _currency(raw.get("amount_currency")) if (amin or amax) else None,
            "amount_status": amount_status,
            "amount_note": raw.get("amount_note") or None,
            "deadline_mode": _enum(raw.get("deadline_mode"), DEADLINE_MODES, "unknown"),
            "is_accepting": raw.get("is_accepting") if isinstance(raw.get("is_accepting"), bool) else None,
            "apply_url": _url(raw.get("apply_url")),
        })
    else:
        fmin, fmax = backed_amount("fee_min", "fee"), backed_amount("fee_max", "fee")
        if fmin is not None and fmax is not None and fmin > fmax:
            reject("fee", "fee_min > fee_max", [fmin, fmax])
            fmin = fmax = None
        platform = _enum(raw.get("submit_platform"), PLATFORMS, "unknown")
        if platform != "unknown" and not quotes_for("submit_platform"):
            reject("submit_platform", "no evidence quote", platform)
            platform = "unknown"
        qualifying = []
        for q in raw.get("qualifying") or []:
            if q.get("body") in QUALIFYING_BODIES and quote_found(q.get("source_quote"), doc):
                qualifying.append({"body": q["body"], "category": q.get("category") or None,
                                   "source_quote": q["source_quote"].strip()})
            else:
                reject(f"qualifying:{q.get('body')}", "quote not found in page", q.get("source_quote"))
        year = raw.get("edition_year")
        item.update({
            "event_type": _enum(raw.get("event_type"), EVENT_TYPES, "other"),
            "edition_year": year if isinstance(year, int) and 1900 < year < 2100 else None,
            "format": _enum(raw.get("format"), FORMATS, "unknown"),
            "city": raw.get("city") or None,
            "submit_platform": platform,
            "submit_url": _url(raw.get("submit_url")),
            "fee_min": fmin, "fee_max": fmax,
            "fee_currency": _currency(raw.get("fee_currency")) if (fmin or fmax) else None,
            "fee_note": raw.get("fee_note") or None,
            "genres": [str(g)[:40] for g in raw.get("genres") or []],
            "qualifying": qualifying,
        })
    return item
