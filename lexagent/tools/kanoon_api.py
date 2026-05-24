"""
Indian Kanoon REST API client.

WHY: The Playwright scraper in kanoon.py breaks whenever Indian Kanoon
changes its page structure. The official REST API (api.indiankanoon.org)
is stable, JSON-native, and 10x faster than browser automation.

Set LEX_KANOON_BACKEND=api and KANOON_API_KEY=<your-key> in .env.
API keys available at https://api.indiankanoon.org/
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

KANOON_API_BASE = "https://api.indiankanoon.org"
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_TEXT_CHARS = 15_000  # WHY: matches Playwright scraper cap; keeps LLM context sane


def _strip_html(html: str) -> str:
    """Remove HTML tags — judgment full text from the API arrives as HTML."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s{2,}", " ", text).strip()


class KanoonAPIClient:
    """
    Thin async wrapper around the Indian Kanoon REST API.

    Implements the async context manager protocol so the underlying
    httpx.AsyncClient is always properly closed.

    Usage:
        async with KanoonAPIClient(api_key) as client:
            results = await client.search("Section 138 NI Act cheque dishonour")
            doc     = await client.fetch_doc(results[0]["tid"])
    """

    def __init__(self, api_key: str, base_url: str = KANOON_API_BASE) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "KanoonAPIClient":
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Token {self._api_key}"},
            timeout=_TIMEOUT,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(
        self,
        query: str,
        pagenum: int = 1,
        max_results: int = 5,
    ) -> list[dict]:
        """
        Search Indian Kanoon and return top results.

        Returns a list of dicts shaped to match the existing research_findings
        format so this is a drop-in for kanoon.search_and_fetch results:
            tid, title, docsource, snippet, publishdate, url, citation
        """
        assert self._client is not None, "Must be used as async context manager"
        resp = await self._client.post(
            "/search/",
            data={"formInput": query, "pagenum": pagenum},
        )
        resp.raise_for_status()
        payload = resp.json()
        docs = payload.get("docs", [])[:max_results]
        return [
            {
                "tid": d.get("tid"),
                "title": d.get("title", ""),
                "docsource": d.get("docsource", ""),
                "snippet": _strip_html(d.get("headline", ""))[:500],
                "publishdate": d.get("publishdate", ""),
                "url": f"https://indiankanoon.org/doc/{d.get('tid')}/",
                "citation": d.get("citation", ""),
            }
            for d in docs
        ]

    async def fetch_doc(self, docid: int | str) -> dict:
        """
        Fetch the full text and cited cases for a judgment by doc ID.

        Returns dict with keys: tid, title, full_text, citations_found, status.
        status is "success" if full_text is non-empty, else "empty".
        """
        assert self._client is not None, "Must be used as async context manager"
        resp = await self._client.post(f"/doc/{docid}/")
        resp.raise_for_status()
        payload = resp.json()
        raw_doc = payload.get("doc", "")
        full_text = _strip_html(raw_doc)[:_MAX_TEXT_CHARS]

        raw_cites = payload.get("citations", [])
        citations_found = [
            {
                "case_name": c.get("title", ""),
                "url": f"https://indiankanoon.org/doc/{c.get('tid')}/",
            }
            for c in raw_cites[:20]
        ]

        return {
            "tid": payload.get("tid"),
            "title": payload.get("title", ""),
            "full_text": full_text,
            "citations_found": citations_found,
            "status": "success" if full_text else "empty",
        }


async def search_and_fetch_api(
    query: str,
    api_key: str,
    max_results: int = 3,
    base_url: str = KANOON_API_BASE,
) -> dict:
    """
    End-to-end: search then fetch full text for each result.

    Returns the same shape as kanoon.search_and_fetch so research.py can
    swap backends without changing downstream code:
        {"query": str, "results": [merged_search_and_doc_dicts]}
    """
    async with KanoonAPIClient(api_key, base_url=base_url) as client:
        try:
            hits = await client.search(query, max_results=max_results)
            enriched: list[dict] = []
            for hit in hits:
                doc = await client.fetch_doc(hit["tid"])
                enriched.append({**hit, **doc})
            return {"query": query, "results": enriched}
        except httpx.HTTPStatusError as e:
            return {
                "query": query,
                "results": [],
                "error": f"Kanoon API HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            return {"query": query, "results": [], "error": str(e)}
