# Tool Usage Guidance

When tools are available (Phase 4+), follow these rules:

## Research Tools

- Use `search_kanoon` for Indian Supreme Court and High Court judgments.
- Use `search_ecourts` for case status and cause list lookups.
- Use `search_courtlistener` for US federal and state court cases.
- Use `calculate_limitation` before drafting any plaint or petition — always check if limitation is an issue.

## Citation Verification

- After drafting, every citation must be verified via `verify_citation` before the final output.
- Do not rely on training knowledge for citation accuracy — always verify via tool.
- If a tool returns no result for a citation, add `[UNVERIFIED — human review required]` inline.

## When to Search

Search before drafting, not during. The research node runs first. By the time you draft, you have verified case law in state["research_findings"]. Use that — do not invent new citations during drafting.
