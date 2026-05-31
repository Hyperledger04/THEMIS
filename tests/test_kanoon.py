"""
Live Playwright smoke tests for the Indian Kanoon scraper.
These tests open a real headed/headless Chrome — they require internet access.
Run with: pytest tests/test_kanoon.py -v
"""

import pytest
from lexagent.tools.kanoon import search_and_fetch
from lexagent.tools.kanoon_utils import fix_doc_url


# ---------------------------------------------------------------------------
# URL normalisation — no browser or network required
# ---------------------------------------------------------------------------

def test_fix_doc_url_converts_fragment_to_full():
    result = fix_doc_url("/docfragment/12345678/?formInput=foo")
    assert result == "https://indiankanoon.org/doc/12345678/"


def test_fix_doc_url_strips_query_from_doc_url():
    result = fix_doc_url("/doc/12345678/?something=extra")
    assert result == "https://indiankanoon.org/doc/12345678/"


def test_fix_doc_url_already_clean():
    result = fix_doc_url("https://indiankanoon.org/doc/12345678/")
    assert result == "https://indiankanoon.org/doc/12345678/"


def test_fix_doc_url_adds_base_for_relative_doc():
    result = fix_doc_url("/doc/99999/")
    assert result == "https://indiankanoon.org/doc/99999/"


@pytest.mark.asyncio
async def test_search_returns_results():
    result = await search_and_fetch(
        query="landlord tenant eviction Delhi High Court",
        max_results=2,
        headless=True,
    )
    assert "results" in result
    assert len(result["results"]) > 0, "Expected at least one result from Indian Kanoon"


@pytest.mark.asyncio
async def test_judgment_has_full_text():
    result = await search_and_fetch(
        query="Section 138 Negotiable Instruments Act cheque dishonour",
        max_results=1,
        headless=True,
    )
    assert result["results"], "No results returned"
    first = result["results"][0]
    assert first.get("status") == "success", f"Fetch failed: {first.get('error')}"
    assert len(first.get("full_text", "")) > 500, "Judgment text too short — likely not scraped"


@pytest.mark.asyncio
async def test_citations_extracted():
    result = await search_and_fetch(
        query="specific performance contract Supreme Court India",
        max_results=1,
        headless=True,
    )
    first = result["results"][0] if result["results"] else {}
    assert "citations_found" in first, "citations_found key missing from result"
