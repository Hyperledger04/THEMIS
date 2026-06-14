# Perplexity API — answers with inline citations.
# Requires PERPLEXITY_API_KEY. Implementation coming in a later phase.

from themis.tools.registry import ToolRegistry


@ToolRegistry.register(
    name="perplexity_search",
    description="AI-powered search with inline citations via Perplexity (requires PERPLEXITY_API_KEY).",
    schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def perplexity_search_tool(query: str) -> dict:
    # TODO: implement with httpx + api.perplexity.ai
    return {"results": [], "status": "stub — Perplexity not yet implemented"}
