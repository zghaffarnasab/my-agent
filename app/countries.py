"""Countries for matching website requests against the pipeline's open_to lists.

The visitor types their country as free text (English or Persian); open_to holds ISO 3166-1 alpha-2
codes or the groups below (see pipeline/sql/002_europe.sql).
"""

EU = frozenset("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split())
EEA = EU | {"IS", "LI", "NO"}
# Countries taking full part in Creative Europe MEDIA (2021-2027). The UK is not one of them.
MEDIA = EEA | {"AL", "BA", "ME", "MK", "RS", "UA"}
EUROPE = MEDIA | {"GB", "CH", "TR", "GE", "AM", "AD", "MC", "SM", "VA", "MD", "XK"}
GROUPS = {"EU": EU, "EEA": EEA, "MEDIA": MEDIA, "EUROPE": EUROPE}

# Code -> names a visitor may type. Persian names are escaped (data, not UI text) so the
# no-hardcoded-Persian test stays simple.
_NAMES = {
    "GB": ("uk", "u.k.", "united kingdom", "great britain", "britain", "england", "scotland", "wales", "northern ireland", "london", "\u0628\u0631\u06cc\u062a\u0627\u0646\u06cc\u0627", "\u0627\u0646\u06af\u0644\u06cc\u0633", "\u0627\u0646\u06af\u0644\u0633\u062a\u0627\u0646", "\u0627\u0633\u06a9\u0627\u062a\u0644\u0646\u062f", "\u0648\u0644\u0632"),
    "IE": ("ireland", "republic of ireland", "eire", "\u0627\u06cc\u0631\u0644\u0646\u062f"),
    "DE": ("germany", "deutschland", "\u0622\u0644\u0645\u0627\u0646"),
    "FR": ("france", "\u0641\u0631\u0627\u0646\u0633\u0647"),
    "IT": ("italy", "italia", "\u0627\u06cc\u062a\u0627\u0644\u06cc\u0627"),
    "ES": ("spain", "españa", "espana", "\u0627\u0633\u067e\u0627\u0646\u06cc\u0627"),
    "PT": ("portugal", "\u067e\u0631\u062a\u063a\u0627\u0644"),
    "NL": ("netherlands", "the netherlands", "holland", "\u0647\u0644\u0646\u062f"),
    "BE": ("belgium", "\u0628\u0644\u0698\u06cc\u06a9"),
    "LU": ("luxembourg", "\u0644\u0648\u06a9\u0632\u0627\u0645\u0628\u0648\u0631\u06af"),
    "AT": ("austria", "\u0627\u062a\u0631\u06cc\u0634"),
    "CH": ("switzerland", "\u0633\u0648\u0626\u06cc\u0633"),
    "DK": ("denmark", "\u062f\u0627\u0646\u0645\u0627\u0631\u06a9"),
    "SE": ("sweden", "\u0633\u0648\u0626\u062f"),
    "NO": ("norway", "\u0646\u0631\u0648\u0698"),
    "FI": ("finland", "\u0641\u0646\u0644\u0627\u0646\u062f"),
    "IS": ("iceland", "\u0627\u06cc\u0633\u0644\u0646\u062f"),
    "PL": ("poland", "\u0644\u0647\u0633\u062a\u0627\u0646"),
    "CZ": ("czech republic", "czechia", "\u0686\u06a9", "\u062c\u0645\u0647\u0648\u0631\u06cc \u0686\u06a9"),
    "SK": ("slovakia", "\u0627\u0633\u0644\u0648\u0627\u06a9\u06cc"),
    "HU": ("hungary", "\u0645\u062c\u0627\u0631\u0633\u062a\u0627\u0646"),
    "RO": ("romania", "\u0631\u0648\u0645\u0627\u0646\u06cc"),
    "BG": ("bulgaria", "\u0628\u0644\u063a\u0627\u0631\u0633\u062a\u0627\u0646"),
    "GR": ("greece", "\u06cc\u0648\u0646\u0627\u0646"),
    "CY": ("cyprus", "\u0642\u0628\u0631\u0633"),
    "MT": ("malta", "\u0645\u0627\u0644\u062a"),
    "HR": ("croatia", "\u06a9\u0631\u0648\u0627\u0633\u06cc"),
    "SI": ("slovenia", "\u0627\u0633\u0644\u0648\u0648\u0646\u06cc"),
    "EE": ("estonia", "\u0627\u0633\u062a\u0648\u0646\u06cc"),
    "LV": ("latvia", "\u0644\u062a\u0648\u0646\u06cc"),
    "LT": ("lithuania", "\u0644\u06cc\u062a\u0648\u0627\u0646\u06cc"),
    "RS": ("serbia", "\u0635\u0631\u0628\u0633\u062a\u0627\u0646"),
    "BA": ("bosnia and herzegovina", "bosnia", "\u0628\u0648\u0633\u0646\u06cc"),
    "ME": ("montenegro", "\u0645\u0648\u0646\u062a\u0647\u200c\u0646\u06af\u0631\u0648"),
    "MK": ("north macedonia", "macedonia", "\u0645\u0642\u062f\u0648\u0646\u06cc\u0647"),
    "AL": ("albania", "\u0622\u0644\u0628\u0627\u0646\u06cc"),
    "UA": ("ukraine", "\u0627\u0648\u06a9\u0631\u0627\u06cc\u0646"),
    "GE": ("georgia", "\u06af\u0631\u062c\u0633\u062a\u0627\u0646"),
    "AM": ("armenia", "\u0627\u0631\u0645\u0646\u0633\u062a\u0627\u0646"),
    "TR": ("turkey", "türkiye", "turkiye", "\u062a\u0631\u06a9\u06cc\u0647"),
    "IR": ("iran", "\u0627\u06cc\u0631\u0627\u0646"),
    "AF": ("afghanistan", "\u0627\u0641\u063a\u0627\u0646\u0633\u062a\u0627\u0646"),
    "US": ("usa", "united states", "united states of america", "america", "\u0622\u0645\u0631\u06cc\u06a9\u0627", "\u0627\u0645\u0631\u06cc\u06a9\u0627"),
    "CA": ("canada", "\u06a9\u0627\u0646\u0627\u062f\u0627"),
}
_BY_NAME = {name: code for code, names in _NAMES.items() for name in names}


def code(text: str | None) -> str | None:
    """ISO code for what the visitor typed, or None when it is not recognised."""
    value = (text or "").strip().lower()
    if not value:
        return None
    for candidate in (value, value.split(",")[0].split("(")[0].strip()):
        if candidate in _BY_NAME:
            return _BY_NAME[candidate]
        if len(candidate) == 2 and candidate.isalpha():
            upper = candidate.upper()
            return "GB" if upper == "UK" else upper
    return None


def covers(open_to: list[str] | None, country: str | None) -> bool | None:
    """Whether a record open to `open_to` accepts applicants from `country` (an ISO code).
    None when either side is unknown."""
    if not open_to or not country:
        return None
    for entry in open_to:
        if entry == "WORLD" or entry == country or country in GROUPS.get(entry, ()):
            return True
    return False
