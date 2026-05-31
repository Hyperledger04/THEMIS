# CourtListener — US court opinions and dockets.
# Requires COURTLISTENER_API_KEY. Implementation coming in a later phase.

from lexagent.tools.registry import ToolRegistry


@ToolRegistry.register(
    name="courtlistener_search",
    description="US court opinions via CourtListener (requires COURTLISTENER_API_KEY).",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
)
def courtlistener_search_tool(query: str, max_results: int = 5) -> dict:
    # TODO: implement with https://www.courtlistener.com/api/rest/v4/
    return {"results": [], "status": "stub — CourtListener not yet implemented"}
