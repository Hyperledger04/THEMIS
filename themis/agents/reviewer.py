# ReviewerAgent — wraps cite (optional) + review nodes with specialist contract.
#
# cite runs only when auto_verify_citations=True AND research_findings exist.
# review validates the draft, writes the .docx, and produces a structured review_result.
# The review_result handoff slot is set here for Senior Counsel to read after dispatch.

from __future__ import annotations

import logging

from themis.config import LexConfig
from themis.nodes import cite, review
from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)


async def run(state: SeniorCounselState) -> dict:
    """
    ReviewerAgent node — dispatched by Senior Counsel via send().

    1. Optionally runs cite (citation verification gate).
    2. Runs review (draft validation + .docx output).
    3. Builds review_result handoff slot for Senior Counsel.
    4. Pops reviewer from execution_plan.
    """
    try:
        cfg = LexConfig()
        working: SeniorCounselState = dict(state)  # type: ignore[assignment]

        # Step 1: citation verification gate (conditional)
        # WHY: cite runs only when research findings exist — legal notices / affidavits
        # have no findings to verify, so we skip cite entirely for those paths.
        if cfg.auto_verify_citations and state.get("research_findings"):
            cite_result = await cite.run(working)
            working = {
                **working,
                **{k: v for k, v in cite_result.items() if v is not None},
            }  # type: ignore[assignment]

        # Step 2: review — validate draft, write .docx, compute risk annotations
        review_result_raw = await review.run(working)

        # Build the structured review_result handoff slot.
        # WHY: The existing review node doesn't set review_result as a key; it sets
        # risk_annotations, docx_path, etc. We construct review_result here so Senior
        # Counsel and future ReviewerState subgraphs have a typed handoff slot.
        risk = review_result_raw.get("risk_annotations") or []
        severity_map = {"H": "critical", "M": "major", "L": "minor"}
        issues = [
            {
                "clause": a.get("clause", ""),
                "severity": severity_map.get(a.get("risk_level", "L"), "minor"),
                "note": a.get("note", ""),
            }
            for a in risk
        ]
        has_critical = any(i["severity"] == "critical" for i in issues)
        review_result = {
            "passed": not has_critical,
            "issues": issues,
            "risk_score": sum(
                {"critical": 1.0, "major": 0.5, "minor": 0.1}.get(i["severity"], 0)
                for i in issues
            ) / max(len(issues), 1) if issues else 0.0,
        }

        # Pop reviewer from execution_plan
        new_plan = (state.get("execution_plan") or [])[1:]

        return {
            **review_result_raw,
            "review_result": review_result,
            "execution_plan": new_plan,
            "active_specialist": None,
            "status": "reviewing",
        }
    except Exception as e:
        logger.exception("ReviewerAgent failed")
        return {
            "error": f"ReviewerAgent: {e}",
            "execution_plan": [],
            "active_specialist": None,
        }
