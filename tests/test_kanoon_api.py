"""Tests for lexagent/tools/kanoon_api.py — all HTTP calls mocked via respx."""
import pytest
import respx
import httpx

from lexagent.tools.kanoon_api import KanoonAPIClient, search_and_fetch_api

_BASE = "https://api.indiankanoon.org"

_SEARCH_PAYLOAD = {
    "docs": [
        {
            "tid": 41816547,
            "title": "K.Veeraiah vs Ganesh Credits on 1 November, 2012",
            "docsource": "Andhra High Court",
            "headline": "<b>Section 138</b> Negotiable Instruments Act cheque dishonour",
            "publishdate": "2012-11-01",
            "citation": "2013 CriLJ 111",
        }
    ]
}

_DOC_PAYLOAD = {
    "tid": 41816547,
    "title": "K.Veeraiah vs Ganesh Credits on 1 November, 2012",
    "doc": "<p>The cheque was dishonoured by the bank. The court held that under Section 138 NI Act the accused is liable.</p>",
    "citations": [
        {"tid": 1234, "title": "Rangappa v Sri Mohan"},
        {"tid": 5678, "title": "Dashrath Rupsingh Rathod v State of Maharashtra"},
    ],
}


@pytest.fixture()
def mock_kanoon():
    """respx mock that intercepts both /search/ and /doc/{id}/ calls."""
    with respx.mock(base_url=_BASE, assert_all_called=False) as m:
        m.post("/search/").mock(return_value=httpx.Response(200, json=_SEARCH_PAYLOAD))
        m.post("/doc/41816547/").mock(return_value=httpx.Response(200, json=_DOC_PAYLOAD))
        yield m


# ---------------------------------------------------------------------------
# KanoonAPIClient.search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_list(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        results = await client.search("Section 138 NI Act")
    assert isinstance(results, list)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_result_has_required_keys(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        results = await client.search("cheque dishonour")
    r = results[0]
    for key in ("tid", "title", "docsource", "snippet", "url", "citation"):
        assert key in r, f"Missing key: {key}"


@pytest.mark.asyncio
async def test_search_url_format(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        results = await client.search("cheque dishonour")
    assert results[0]["url"] == "https://indiankanoon.org/doc/41816547/"


@pytest.mark.asyncio
async def test_search_strips_html_from_snippet(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        results = await client.search("cheque dishonour")
    snippet = results[0]["snippet"]
    assert "<b>" not in snippet
    assert "Section 138" in snippet


@pytest.mark.asyncio
async def test_search_respects_max_results():
    many_docs = {
        "docs": [
            {"tid": i, "title": f"Case {i}", "docsource": "SC", "headline": "", "publishdate": "2023-01-01"}
            for i in range(10)
        ]
    }
    with respx.mock(base_url=_BASE) as m:
        m.post("/search/").mock(return_value=httpx.Response(200, json=many_docs))
        async with KanoonAPIClient("key", base_url=_BASE) as client:
            results = await client.search("anything", max_results=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# KanoonAPIClient.fetch_doc
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_doc_status_success(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        doc = await client.fetch_doc(41816547)
    assert doc["status"] == "success"


@pytest.mark.asyncio
async def test_fetch_doc_full_text_populated(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        doc = await client.fetch_doc(41816547)
    assert "cheque" in doc["full_text"]
    assert "Section 138" in doc["full_text"]


@pytest.mark.asyncio
async def test_fetch_doc_strips_html(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        doc = await client.fetch_doc(41816547)
    assert "<p>" not in doc["full_text"]
    assert "<b>" not in doc["full_text"]


@pytest.mark.asyncio
async def test_fetch_doc_citations_shape(mock_kanoon):
    async with KanoonAPIClient("test-key", base_url=_BASE) as client:
        doc = await client.fetch_doc(41816547)
    assert isinstance(doc["citations_found"], list)
    cite = doc["citations_found"][0]
    assert "case_name" in cite
    assert "url" in cite
    assert cite["url"].startswith("https://indiankanoon.org/doc/")


@pytest.mark.asyncio
async def test_fetch_doc_empty_when_no_text():
    empty_doc = {"tid": 999, "title": "Empty", "doc": "", "citations": []}
    with respx.mock(base_url=_BASE) as m:
        m.post("/doc/999/").mock(return_value=httpx.Response(200, json=empty_doc))
        async with KanoonAPIClient("key", base_url=_BASE) as client:
            doc = await client.fetch_doc(999)
    assert doc["status"] == "empty"


# ---------------------------------------------------------------------------
# search_and_fetch_api — end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_and_fetch_api_end_to_end(mock_kanoon):
    result = await search_and_fetch_api(
        "Section 138 NI Act cheque dishonour",
        api_key="test-key",
        max_results=3,
        base_url=_BASE,
    )
    assert result["query"] == "Section 138 NI Act cheque dishonour"
    assert len(result["results"]) == 1
    first = result["results"][0]
    assert first["status"] == "success"
    assert "full_text" in first
    assert "citations_found" in first


@pytest.mark.asyncio
async def test_search_and_fetch_api_merges_search_and_doc_fields(mock_kanoon):
    result = await search_and_fetch_api("cheque dishonour", api_key="key", base_url=_BASE)
    first = result["results"][0]
    # From search: snippet, docsource, publishdate
    assert "snippet" in first
    assert "docsource" in first
    # From fetch_doc: full_text, citations_found
    assert "full_text" in first
    assert "citations_found" in first


@pytest.mark.asyncio
async def test_search_and_fetch_api_on_http_error():
    with respx.mock(base_url=_BASE) as m:
        m.post("/search/").mock(return_value=httpx.Response(403, text="Forbidden"))
        result = await search_and_fetch_api("anything", api_key="bad-key", base_url=_BASE)
    assert result["results"] == []
    assert "error" in result
    assert "403" in result["error"]


@pytest.mark.asyncio
async def test_search_and_fetch_api_on_network_error():
    with respx.mock(base_url=_BASE) as m:
        m.post("/search/").mock(side_effect=httpx.ConnectError("connection refused"))
        result = await search_and_fetch_api("anything", api_key="key", base_url=_BASE)
    assert result["results"] == []
    assert "error" in result
