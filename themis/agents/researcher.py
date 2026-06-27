# ResearcherAgent — wraps the existing react_research node with specialist contract.
#
# Node contract (same as all nodes):
#   async def run(state: SeniorCounselState) -> dict
#   Returns only changed keys. Never raises — catches and sets state["error"].
#
# WHY this wrapper exists: Senior Counsel dispatches here via send().
# In V3.3 this is a thin adapter. In R1, this becomes the full ReAct investigation loop
# with kanoon_api, tavily_search, citation gate, and Qdrant sync indexing.

from __future__ import annotations

import logging

from themis.nodes import react_research
from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)


async def run(state: SeniorCounselState) -> dict:
    """
    ResearcherAgent node — dispatched by Senior Counsel via send().

    Calls the existing react_research node, then pops this specialist
    from execution_plan so coordinate advances to the next step.
    """
    try:
        # WHY: react_research.run() takes SeniorCounselState and returns partial dict.
        # ResearcherState fields (search_queries, tool_calls_log, thread_messages) are
        # internal audit fields — not yet present in SeniorCounselState. They will be
        # added when the full ReAct loop ships in R1.
        result = await react_research.run(state)

        # Pop researcher from execution_plan (Senior Counsel's coordination loop)
        new_plan = (state.get("execution_plan") or [])[1:]

        return {
            **result,
            "execution_plan": new_plan,
            "active_specialist": None,
            "status": "researching",
        }
    except Exception as e:
        logger.exception("ResearcherAgent failed")
        return {
            "error": f"ResearcherAgent: {e}",
            "execution_plan": [],   # abort plan on unrecoverable error
            "active_specialist": None,
        }
