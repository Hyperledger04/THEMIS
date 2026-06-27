# DrafterAgent — wraps retrieve + draft nodes with specialist contract.
#
# Retrieve enriches the state with template-grounded context (RAG chunks).
# Draft generates the court-ready document using enriched state + SOUL.md style.
# Chamber review is NOT included here — it runs as a conditional step inside draft routing
# (see route_after_draft in senior_counsel.py) so it can be toggled with --chamber.

from __future__ import annotations

import logging

from themis.nodes import draft, retrieve
from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)


async def run(state: SeniorCounselState) -> dict:
    """
    DrafterAgent node — dispatched by Senior Counsel via send().

    1. Runs retrieve to ground context with RAG chunks.
    2. Merges retrieve output into working state.
    3. Runs draft to produce the document.
    4. Pops drafter from execution_plan.
    """
    try:
        # Step 1: retrieve — template and case-law grounding
        retrieve_result = await retrieve.run(state)
        # WHY: Merge retrieve output into working state before draft so the draft node
        # sees retrieval_chunks and grounded_citations. Don't overwrite with None values.
        working: SeniorCounselState = {
            **state,
            **{k: v for k, v in retrieve_result.items() if v is not None},
        }  # type: ignore[assignment]

        # Step 2: draft — generate the document
        draft_result = await draft.run(working)

        # Pop drafter from execution_plan
        new_plan = (state.get("execution_plan") or [])[1:]

        return {
            **draft_result,
            "execution_plan": new_plan,
            "active_specialist": None,
            "status": "drafting",
        }
    except Exception as e:
        logger.exception("DrafterAgent failed")
        return {
            "error": f"DrafterAgent: {e}",
            "execution_plan": [],
            "active_specialist": None,
        }
