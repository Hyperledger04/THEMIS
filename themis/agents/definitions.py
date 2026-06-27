# LANGGRAPH: Agent definitions follow the Lavern pattern — each agent is a plain dict,
# not a class. Dicts are serialisable, patchable at runtime, and configurable per-lawyer
# without code changes. The definition describes WHAT an agent is; profiles.py says HOW.

from __future__ import annotations

# WHY: Defaults live here so they can be imported before LexConfig is instantiated.
# LexConfig overrides these at graph-build time via agent_profiles["*"]["model"].
SENIOR_COUNSEL_MODEL = "claude-opus-4-8"
RESEARCHER_MODEL     = "claude-sonnet-4-6"
DRAFTER_MODEL        = "claude-opus-4-8"   # draft is the product — use best model
REVIEWER_MODEL       = "claude-sonnet-4-6"
VERIFICATION_MODEL   = "claude-sonnet-4-6"

AGENT_DEFINITIONS: dict[str, dict] = {
    "senior_counsel": {
        "name": "Senior Counsel",
        "description": (
            "Orchestrates all specialist agents. Owns matter intake, execution planning, "
            "memory reads/writes, persist_matter() calls, and final output delivery to the lawyer."
        ),
        "model": SENIOR_COUNSEL_MODEL,
        "max_turns": 5,
        "output_format": "Delegates to specialists; final state is SeniorCounselState.",
    },
    "researcher": {
        "name": "Research Counsel",
        "description": (
            "Plans a research strategy, executes Indian Kanoon / Tavily / eCourts queries, "
            "verifies citations against primary sources, and returns a structured findings list. "
            "Never fabricates a citation — drops unverifiable findings with a reason tag."
        ),
        "model": RESEARCHER_MODEL,
        "max_turns": 20,
        "output_format": "list[dict] — [{title, citation, doc_excerpt, url, verified: bool}]",
    },
    "drafter": {
        "name": "Drafting Counsel",
        "description": (
            "Drafts court-ready legal documents — pleadings, notices, affidavits, applications — "
            "using verified research findings and the lawyer's SOUL.md style preferences. "
            "Follows the active skill's structural template."
        ),
        "model": DRAFTER_MODEL,
        "max_turns": 10,
        "output_format": "str — full draft text with section headings and exhibit references.",
    },
    "reviewer": {
        "name": "Review Counsel",
        "description": (
            "Reviews the draft for legal validity, procedural compliance, citation accuracy, "
            "logical coherence, and client risk. Produces a structured review result. "
            "Flags unverified citations for the verification specialist."
        ),
        "model": REVIEWER_MODEL,
        "max_turns": 10,
        "output_format": "dict — {passed: bool, issues: [...], risk_score: float}",
    },
    "verification": {
        "name": "Citation Counsel",
        "description": (
            "Verifies each citation against primary sources using browser-based tools. "
            "Extracts the ratio decidendi, checks proposition alignment, and produces "
            "tri-state status: verified | partial | contradicted. "
            "Blocks output on 'contradicted'; flags 'partial' explicitly."
        ),
        "model": VERIFICATION_MODEL,
        "max_turns": 30,
        "output_format": "dict — {verified: [...], failed: [...], confidence: {citation: float}}",
    },
}
