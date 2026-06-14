# DuckDuckGo web search — free, no API key required.
# Uses the duckduckgo-search library (ddgs).

from rich.console import Console

from themis.tools.registry import ToolRegistry

console = Console()


def search_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """
    Search DuckDuckGo and return structured results.
    Returns list of {title, url, snippet}.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "full_text": "",
                    "source": "duckduckgo",
                })
        return results
    except ImportError:
        console.print("[yellow]duckduckgo-search not installed — run: uv add duckduckgo-search[/yellow]")
        return []
    except Exception as exc:
        console.print(f"[yellow]DuckDuckGo search error: {exc}[/yellow]")
        return []


@ToolRegistry.register(
    name="duckduckgo_search",
    description="Free web search via DuckDuckGo (no API key required).",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
def duckduckgo_search_tool(query: str, max_results: int = 5) -> dict:
    results = search_duckduckgo(query, max_results)
    return {"results": results}
