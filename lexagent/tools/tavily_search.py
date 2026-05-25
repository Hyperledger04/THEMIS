"""
Tavily web search tool for Indian legal research.

WHY: Indian Kanoon covers judgments but not statutory texts, gazette
notifications, SEBI circulars, RBI master directions, or law commission
reports. Tavily fills that gap with deep-web search and structured snippets.

Registered in ToolRegistry when LEX_TAVILY_ENABLED=true AND
LEX_TAVILY_API_KEY is set. Returns [] gracefully when disabled — no errors
propagate to the research node so offline/stub runs are unaffected.
"""
from __future__ import annotations

import asyncio
from typing import Any

from lexagent.tools.registry import ToolRegistry


def _is_enabled() -> bool:
    """Check config at call time so tests can patch LexConfig fields."""
    from lexagent.config import LexConfig
    cfg = LexConfig()
    return bool(cfg.tavily_enabled and cfg.tavily_api_key)


async def _search_async(query: str, max_results: int = 5) -> list[dict]:
    """
    Async Tavily search. Returns [] when Tavily is disabled or key is absent.
    """
    if not _is_enabled():
        return []

    from lexagent.config import LexConfig
    cfg = LexConfig()

    try:
        # WHY: lazy import — tavily-python is an optional extra; importing at
        # module level would crash startup when the package is not installed.
        from tavily import AsyncTavilyClient  # type: ignore[import]
        client = AsyncTavilyClient(api_key=cfg.tavily_api_key)
        response = await client.search(
            query,
            max_results=max_results,
            search_depth="advanced",
            include_answer=False,
        )
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:1_000],
                "score": r.get("score", 0.0),
                "source": "tavily",
            }
            for r in response.get("results", [])
        ]
    except ImportError:
        return [{"error": "tavily-python not installed; run: uv add tavily-python", "source": "tavily"}]
    except Exception as e:
        return [{"error": str(e), "source": "tavily"}]


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """Sync wrapper for use in ToolRegistry (sync context)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async context (e.g., research node) — caller
            # should call _search_async directly.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _search_async(query, max_results))
                return future.result()
        return loop.run_until_complete(_search_async(query, max_results))
    except Exception as e:
        return [{"error": str(e), "source": "tavily"}]


@ToolRegistry.register(
    name="web_search",
    description=(
        "Search the web for Indian statutory texts, gazette notifications, "
        "SEBI/RBI circulars, law commission reports, and recent legal news. "
        "Returns title, url, content snippet, and relevance score per result."
    ),
    schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Legal search query in plain English or Indian legal terminology",
            },
            "max_results": {
                "type": "integer",
                "default": 5,
                "description": "Maximum number of results to return (1–10)",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Synchronous entry point used by ToolRegistry callers."""
    return _search_sync(query, max_results)


async def web_search_async(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Async entry point for direct use inside async nodes (research, react_research)."""
    return await _search_async(query, max_results)
