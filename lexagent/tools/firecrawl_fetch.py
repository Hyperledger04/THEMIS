# Firecrawl — reliable structured web scraping.
# Requires FIRECRAWL_API_KEY. Implementation coming in a later phase.

from lexagent.tools.registry import ToolRegistry


@ToolRegistry.register(
    name="firecrawl_fetch",
    description="Reliable structured scraping via Firecrawl (requires FIRECRAWL_API_KEY).",
    schema={
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    },
)
def firecrawl_fetch_tool(url: str) -> dict:
    # TODO: implement with firecrawl-py SDK
    return {"content": "", "status": "stub — Firecrawl not yet implemented"}
