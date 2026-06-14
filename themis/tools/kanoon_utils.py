import re

KANOON_BASE = "https://indiankanoon.org"


def fix_doc_url(href: str) -> str:
    """
    Convert a /docfragment/{id}/ AJAX href to the full /doc/{id}/ page URL.

    WHY: Indian Kanoon search results link to /docfragment/{id}/?formInput=...
    which is an AJAX fragment endpoint — navigating to it directly gives a raw
    HTML snippet with no .judgments div. The real judgment page is /doc/{id}/.
    This utility is the single source of truth for that normalisation so every
    tool (Playwright path, Jina Reader verification pass, etc.) uses the same logic.
    """
    fixed = re.sub(r"/docfragment/(\d+)/.*", r"/doc/\1/", href)
    fixed = re.sub(r"(/doc/\d+/).*", r"\1", fixed)
    if fixed.startswith("/"):
        fixed = KANOON_BASE + fixed
    return fixed


def is_kanoon_url(url: str) -> bool:
    """Return True if the URL belongs to indiankanoon.org."""
    return "indiankanoon.org" in url
