# legislation.gov.in scraper — official Indian statute portal.
# No API key required. Implementation coming in a later phase.

from lexagent.tools.registry import ToolRegistry


@ToolRegistry.register(
    name="legislation_scraper",
    description="Fetch statute text from legislation.gov.in (no API key required).",
    schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
def legislation_scraper_tool(query: str) -> dict:
    # TODO: implement with httpx scraping of https://www.indiacode.nic.in
    return {"results": [], "status": "stub — legislation scraper not yet implemented"}
