# Tool arrays — shared constants used when binding tools to specialist agents.
# Keeping these here (not inline in each specialist) means adding a tool = one-line change.
# WHY: §6.2 of V3 architecture — specialist tool access is role-scoped, not global.

from __future__ import annotations

# Read-only knowledge tools — any specialist can use these
read_only_tools: list[str] = [
    "read_file",
    "search_kb",
    "list_matter_docs",
]

# Debate board tools — post/challenge/respond to findings (mcp__lex__ server)
debate_tools: list[str] = [
    "post_finding",
    "decline_to_find",
    "post_challenge",
    "post_response",
    "get_findings",
    "get_debate_summary",
    "get_unresolved_debates",
]

# Memory read tools — specialists query, Senior Counsel writes
memory_read_tools: list[str] = [
    "query_matter_memory",
    "query_lawyer_profile",
    "query_precedents",
]

# Memory write tools — Senior Counsel only. Specialists never call these directly.
memory_write_tools: list[str] = [
    "save_matter_memory",
    "save_precedent",
]

# Verification browser stack (R1+ — browser-use, Stagehand, Skyvern, Bright Data MCP)
verification_tools: list[str] = [
    "run_citation_verification",
    "run_cross_verification",
]

browser_tools: list[str] = [
    "browser_use_navigate",
    "stagehand_extract",
    "skyvern_act",
    "brightdata_fetch",
]

# Research tools (R1 — kanoon, tavily, ecourts)
research_tools: list[str] = [
    "kanoon_search",
    "kanoon_fetch",
    "tavily_search",
    "ecourts_lookup",
]

# Researcher gets: research + read-only + debate (for posting findings)
RESEARCHER_TOOLS: list[str] = research_tools + read_only_tools + debate_tools

# Drafter gets: read-only + memory read (needs research findings, soul)
DRAFTER_TOOLS: list[str] = read_only_tools + memory_read_tools

# Reviewer gets: read-only + debate (for challenging weak findings)
REVIEWER_TOOLS: list[str] = read_only_tools + debate_tools

# Verification gets: browser + verification
VERIFICATION_TOOLS: list[str] = verification_tools + browser_tools
