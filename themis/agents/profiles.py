# Agent profiles — HOW each agent should perform.
# Separate from definitions.py (WHAT each agent is) so that performance tuning
# never touches the structural identity of an agent.
#
# MATTER_TYPE_PLANS: rule-based defaults for Indian litigation (covers ~90% of matters).
# SPECIALIST_WHITELIST: LLM-generated plans are validated against this — hallucinated
# specialists are blocked before they reach the graph. (Decision §11, V3 architecture.)

from __future__ import annotations

# ---------------------------------------------------------------------------
# Specialist whitelist — planner cannot invent a specialist not in this set
# ---------------------------------------------------------------------------
SPECIALIST_WHITELIST: frozenset[str] = frozenset(
    {"researcher", "drafter", "reviewer", "verification"}
)

# ---------------------------------------------------------------------------
# Rule-based execution plans (covers ~90% of Indian litigation matter types)
# Each entry is a list of {"specialist": name, "params": {}} dicts.
# Senior Counsel pops entries from the front as each specialist completes.
# ---------------------------------------------------------------------------
_RESEARCH_DRAFT_REVIEW = [
    {"specialist": "researcher", "params": {}},
    {"specialist": "drafter",   "params": {}},
    {"specialist": "reviewer",  "params": {}},
]
_DRAFT_REVIEW_ONLY = [
    {"specialist": "drafter",  "params": {}},
    {"specialist": "reviewer", "params": {}},
]

MATTER_TYPE_PLANS: dict[str, list[dict]] = {
    # Criminal / NI Act
    "ni_act_138":          _RESEARCH_DRAFT_REVIEW,
    "bail":                _RESEARCH_DRAFT_REVIEW,
    "anticipatory_bail":   _RESEARCH_DRAFT_REVIEW,
    "criminal_revision":   _RESEARCH_DRAFT_REVIEW,
    "criminal_appeal":     _RESEARCH_DRAFT_REVIEW,
    # Constitutional / Writ
    "writ_petition":       _RESEARCH_DRAFT_REVIEW,
    "pil":                 _RESEARCH_DRAFT_REVIEW,
    # Civil
    "injunction":          _RESEARCH_DRAFT_REVIEW,
    "civil_suit":          _RESEARCH_DRAFT_REVIEW,
    "specific_performance":_RESEARCH_DRAFT_REVIEW,
    "civil_appeal":        _RESEARCH_DRAFT_REVIEW,
    # Arbitration
    "arbitration":         _RESEARCH_DRAFT_REVIEW,
    "section_9_arb":       _RESEARCH_DRAFT_REVIEW,
    # Document-only (no case law needed)
    "legal_notice":        _DRAFT_REVIEW_ONLY,
    "demand_notice":       _DRAFT_REVIEW_ONLY,
    "affidavit":           _DRAFT_REVIEW_ONLY,
    "vakalatnama":         _DRAFT_REVIEW_ONLY,
    "reply_notice":        _DRAFT_REVIEW_ONLY,
    # Contract work — research not required, reviewer handles clause analysis
    "contract_review":     [{"specialist": "reviewer", "params": {"mode": "contract"}}],
    "contract_draft":      _DRAFT_REVIEW_ONLY,
    # Research-only (lawyer asked only for case law, no document)
    "quick_research":      [{"specialist": "researcher", "params": {}}],
}

# ---------------------------------------------------------------------------
# Agent profiles — success metrics and critical rules injected via enrich_prompt()
# ---------------------------------------------------------------------------
AGENT_PROFILES: dict[str, dict] = {
    "senior_counsel": {
        "critical_rules": [
            "You own all memory reads and writes. Specialists never touch mem0 or Postgres directly.",
            "You are the only agent that calls persist_matter(). Never delegate persistence.",
            "next_action must always be structured JSON. Never free text.",
            "Validate every LLM-generated plan against SPECIALIST_WHITELIST before dispatch.",
        ],
        "success_metrics": [
            "Matter workspace is updated after every specialist completes.",
            "Lawyer receives a clear, actionable summary of what was produced.",
            "Errors are surfaced to the lawyer, never silently swallowed.",
        ],
    },
    "researcher": {
        "critical_rules": [
            "Drop any finding that lacks {title, citation, doc_excerpt, url}. Tag it as unverified.",
            "Never fabricate a citation. If you cannot find a source, say so.",
            "Separate corpus provenance: SC binds all, HC binds within territory, foreign is persuasive only.",
            "Confidence below 0.5 → use decline_to_find, not a low-confidence finding.",
        ],
        "success_metrics": [
            "Every finding in research_findings has verified=True or a reason tag.",
            "Statutes cited are exact section references, not paraphrases.",
            "Limitation period is analysed and stored in limitation_analysis.",
        ],
    },
    "drafter": {
        "critical_rules": [
            "Use only research_findings with verified=True or explicitly flag unverified ones.",
            "Follow the active skill's structural template exactly.",
            "Exhibit references must match the exhibit_registry built during intake.",
            "Never invent a legal proposition not supported by a finding.",
        ],
        "success_metrics": [
            "Draft is court-ready: correct cause number format, prayer, verification.",
            "All cited authorities appear in research_findings.",
            "plain_english_summary is 2-3 lines a client can understand.",
        ],
    },
    "reviewer": {
        "critical_rules": [
            "Flag any citation whose verified=False as 'unverified_citation'.",
            "Never approve a draft that cites a contradicted authority.",
            "Procedural defects (limitation, maintainability, court fee) must be listed as issues.",
            "risk_score must be a float 0.0–1.0; never a string.",
        ],
        "success_metrics": [
            "review_result.passed reflects actual legal validity, not a rubber stamp.",
            "Every issue has a severity: 'critical' | 'major' | 'minor'.",
            "unverified_citations lists every finding with verified=False.",
        ],
    },
    "verification": {
        "critical_rules": [
            "Verification status is tri-state: verified | partial | contradicted. Never binary.",
            "Block final output on 'contradicted'. Flag 'partial' explicitly.",
            "Extract the ratio decidendi paragraph, not just case existence.",
            "Check court hierarchy: does binding value match jurisdiction and court tier?",
        ],
        "success_metrics": [
            "Every citation in unverified_citations gets a tri-state status.",
            "verified_excerpt is stored for every verified citation.",
            "confidence dict maps each citation to a float 0.0–1.0.",
        ],
    },
}


# ---------------------------------------------------------------------------
# enrich_prompt() — appended to every agent's base system prompt
# WHY: Critical rules and success metrics are kept in code (not in the base prompt)
# so they can be updated without touching the prompt files. Every agent gets
# the same structure: rules + metrics + decline_to_find instruction.
# ---------------------------------------------------------------------------
def enrich_prompt(agent_name: str, base_prompt: str) -> str:
    """Append critical rules, success metrics, and confidence gate to a base prompt."""
    profile = AGENT_PROFILES.get(agent_name, {})
    rules = profile.get("critical_rules", [])
    metrics = profile.get("success_metrics", [])

    rules_block = "\n".join(f"- {r}" for r in rules)
    metrics_block = "\n".join(f"- {m}" for m in metrics)

    return f"""{base_prompt}

## Critical Rules (NEVER violate these)
{rules_block}

## Success Metrics (your output is measured by these)
{metrics_block}

## When You Are Not Sure
If you cannot make a confident determination, use the `decline_to_find` tool
instead of posting a finding. A declined finding triggers human review.
A wrong finding causes harm. Confidence threshold: 0.5.
"""


def plan_for_matter(matter_type: str, research_only: bool = False) -> list[dict]:
    """
    Return the execution plan for a matter type.
    Falls back to full research → draft → review for unknown types.
    Respects research_only flag (researcher specialist only).
    """
    if research_only:
        return [{"specialist": "researcher", "params": {}}]

    mt = (matter_type or "").lower().replace(" ", "_").replace("-", "_")
    return list(MATTER_TYPE_PLANS.get(mt, _RESEARCH_DRAFT_REVIEW))
