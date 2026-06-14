# SerpAPI — Google search results with real URLs.
# Requires SERPAPI_API_KEY. Implementation coming in a later phase.

from themis.tools.registry import ToolRegistry


@ToolRegistry.register(
    name="serpapi_search",
    description="Google search results via SerpAPI (requires SERPAPI_API_KEY).",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
def serpapi_search_tool(query: str, max_results: int = 5) -> dict:
    # TODO: implement with httpx + api.serpapi.com
    return {"results": [], "status": "stub — SerpAPI not yet implemented"}
