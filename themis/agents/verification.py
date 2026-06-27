# VerificationAgent — stub for V3.3. Full implementation ships in R1 with browser-use,
# Stagehand, and Skyvern. In V3.3 the agent is registered and dispatched correctly;
# it returns a pass-through verification_result marking all citations as "partial"
# (real: not yet checked via browser) so the draft is not blocked.
#
# WHY stub now: §6.1 and §13 of V3 architecture require VerificationAgent to run as
# a separate ARQ job post-interrupt. The subgraph boundary must exist in V3.3 so
# V3.4 can attach it to the ARQ worker without touching the graph wiring.

from __future__ import annotations

import logging

from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)


async def run(state: SeniorCounselState) -> dict:
    """
    VerificationAgent node — dispatched by Senior Counsel via send().

    V3.3 stub: marks all unverified citations as "partial" (not yet browser-checked).
    R1 replacement: browser-use + Stagehand + Skyvern fetch primary sources,
    extract ratio decidendi, compare propositions, produce tri-state status.
    """
    try:
        unverified = state.get("unverified_citations") or []

        # Stub: tag everything partial until browser verification runs in R1
        verification_result = {
            "verified": [],
            "failed": [],
            "partial": [
                {**c, "status": "partial", "reason": "browser_verification_pending"}
                for c in unverified
            ],
            "confidence": {
                c.get("citation", str(i)): 0.5
                for i, c in enumerate(unverified)
            },
        }

        new_plan = (state.get("execution_plan") or [])[1:]

        logger.info(
            "VerificationAgent stub: %d citations tagged partial (browser verification pending)",
            len(unverified),
        )

        return {
            "verification_result": verification_result,
            "execution_plan": new_plan,
            "active_specialist": None,
            "status": "verifying",
        }
    except Exception as e:
        logger.exception("VerificationAgent failed")
        return {
            "error": f"VerificationAgent: {e}",
            "execution_plan": [],
            "active_specialist": None,
        }
