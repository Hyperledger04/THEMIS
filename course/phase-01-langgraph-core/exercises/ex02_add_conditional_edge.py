"""
Exercise 02 — Add a Research Node with Conditional Routing
===========================================================
Extend your agent from Exercise 01 to match LexAgent's real graph:
  intake → research → draft

Requirements:
  1. Add a research_node that returns a list of case names (stub — no real API)
  2. Add a route_after_research function that:
     - Returns "draft" normally
     - Returns END if research_only=True in state
  3. Wire it up: intake → research → draft
  4. Add a skip_research_types list: for "legal notice" and "affidavit",
     route directly from intake to draft (no research needed)
  5. Add proper error handling to the research node
  6. Run 3 scenarios:
     a. Writ petition → research runs → draft runs
     b. Legal notice → research SKIPPED → draft runs
     c. research_only=True → research runs → END (no draft)

BONUS: Add a 4th scenario where the research node fails with an exception.
       Verify that {"error": "..."} is returned and the graph reaches END cleanly.

python ex02_add_conditional_edge.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

# ──────────────────────────────────────────────
# YOUR TASK
# ──────────────────────────────────────────────

# Build here.

# ──────────────────────────────────────────────
# REFLECTION (fill in after completing)
# ──────────────────────────────────────────────
# 1. What is _NO_RESEARCH_TYPES doing architecturally?
#    (Hint: it's not just about performance)
# 2. If you had 10 document types that skip research, how would you organize this?
# 3. Open lexagent/graph.py and find where _NO_RESEARCH_TYPES is defined.
#    Why is it defined at module level (outside any function)?
# 4. What happens in LexAgent when research_findings is None but draft runs anyway?
#    Trace through draft.py to find out.
