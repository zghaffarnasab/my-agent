"""Sanity checks for the watched-page list in pipeline/sources.json."""
from urllib.parse import urlparse

from pipeline import sources

TIERS = {"official", "aggregator", "press", "newsletter", "unofficial"}
METHODS = {"html", "html_js", "rss", "wp_json", "pdf", "email", "portal"}
KINDS = {"fund", "event"}


def test_every_source_is_valid_and_unique():
    data = sources.load()
    orgs = {o["name"] for o in data["organisations"]}
    urls = set()
    for s in data["sources"]:
        assert urlparse(s["url"]).scheme == "https", s["url"]
        assert s["url"] not in urls, f"duplicate {s['url']}"
        urls.add(s["url"])
        assert s["tier"] in TIERS
        assert s["method"] in METHODS
        assert s["feeds_kind"] in KINDS
        assert s["organisation"] in orgs, s["organisation"]
