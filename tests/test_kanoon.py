"""
Smoke test for the Kanoon Playwright browser tool.
Runs headless so it works in CI. Set LEX_KANOON_HEADLESS=false to watch.
"""

import pytest
from lexagent.tools.kanoon import search_and_fetch


@pytest.mark.asyncio
async def test_search_returns_results():
    result = await search_and_fetch(
        query="landlord tenant eviction Delhi High Court",
        max_results=2,
        headless=True,  # always headless in tests
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
    # citations_found can be empty for older judgments — just assert the key exists
    assert "citations_found" in first, "citations_found key missing from result"
