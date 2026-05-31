# Jina Reader — converts any URL to clean markdown via r.jina.ai.
# Free service, no API key required.
#
# Dual role:
# 1. Research tool: fetch full text of a URL during research
# 2. Verification pass: confirm a cited URL resolves and contains
#    the quoted passage (run after research, before draft)

import httpx
from rich.console import Console

from lexagent.tools.kanoon_utils import fix_doc_url, is_kanoon_url
from lexagent.tools.registry import ToolRegistry

console = Console()

JINA_BASE = "https://r.jina.ai"
_TIMEOUT = 20.0


async def fetch_url_as_markdown(url: str) -> dict:
    """
    Fetch a URL via Jina Reader and return clean markdown text.

    WHY: Jina normalises pages to markdown, stripping nav/ads/JS, giving the
    LLM dense text without needing Playwright. Also works as a cheap verifier —
    if Jina returns 4xx or empty content, the URL is dead or paywalled.
    """
    # Always normalise Kanoon URLs before fetching so we get the full judgment,
    # not the AJAX docfragment endpoint.
    if is_kanoon_url(url):
        url = fix_doc_url(url)

    jina_url = f"{JINA_BASE}/{url}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers={"Accept": "text/markdown"})
        if resp.status_code >= 400:
            return {"url": url, "content": "", "status": resp.status_code, "error": f"HTTP {resp.status_code}"}
        content = resp.text.strip()
        return {"url": url, "content": content, "status": resp.status_code, "error": None}
    except Exception as exc:
        return {"url": url, "content": "", "status": 0, "error": str(exc)}


def verify_citation_in_text(passage: str, full_text: str) -> bool:
    """Return True if passage appears (case-insensitive) in full_text."""
    if not passage or not full_text:
        return False
    return passage.lower().strip() in full_text.lower()


@ToolRegistry.register(
    name="jina_fetch",
    description="Fetch a URL as clean markdown using Jina Reader (free, no key required).",
    schema={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def jina_fetch_sync(url: str) -> dict:
    import asyncio
    return asyncio.run(fetch_url_as_markdown(url))
