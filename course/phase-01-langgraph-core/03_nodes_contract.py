"""
03 — The Node Contract
=======================
Every node in LexAgent follows an exact contract.
Deviate from this contract and the graph breaks in subtle ways.

This file teaches the contract, why every rule exists, and what breaks
when you violate it.

Run this file:
    python 03_nodes_contract.py
"""

import asyncio
from typing import List, Optional, TypedDict


class LexState(TypedDict):
    user_input: str
    matter_type: Optional[str]
    draft_output: Optional[str]
    messages: List[dict]
    error: Optional[str]


# ──────────────────────────────────────────────
# THE NODE CONTRACT — all five rules
# ──────────────────────────────────────────────

print("""
THE NODE CONTRACT:

  Rule 1: Signature is always `async def run(state: LexState) -> dict`
  Rule 2: Read from state with .get() — never []
  Rule 3: Return ONLY the keys you changed — never the full state
  Rule 4: NEVER raise — catch all exceptions, return {"error": str(e)}
  Rule 5: NEVER store state inside the node function itself
""")


# ──────────────────────────────────────────────
# RULE 1: Signature — always async def run(state) -> dict
# ──────────────────────────────────────────────

# CORRECT:
async def intake_node_correct(state: LexState) -> dict:
    return {"matter_type": "writ petition"}

# WRONG — sync function doesn't work with LangGraph's async graph:
def intake_node_wrong_sync(state: LexState) -> dict:
    return {"matter_type": "writ petition"}

# WRONG — wrong return type (returns the whole state):
async def intake_node_wrong_return(state: LexState) -> LexState:
    state["matter_type"] = "writ petition"  # mutates in place — dangerous
    return state                             # returns full state — wastes tokens and can clobber

print("=== Rule 1: Always async def, always returns dict ===")


# ──────────────────────────────────────────────
# RULE 2: Read with .get() — never []
# ──────────────────────────────────────────────
# State fields are Optional. They START as None.
# If a node tries to access a field before it has been set, [] crashes.
# .get() returns None safely.

async def demonstrate_rule2(state: LexState) -> dict:
    # WRONG — crashes if research_findings hasn't been set yet:
    # findings = state["research_findings"]   # KeyError!

    # CORRECT — safe access with fallback:
    findings = state.get("research_findings") or []   # None → []
    messages = state.get("messages") or []            # None → []
    matter_type = state.get("matter_type") or "general petition"

    return {"draft_output": f"Draft for {matter_type} with {len(findings)} findings"}

print("\n=== Rule 2: state.get() not state[] ===")
test_state: LexState = {
    "user_input": "test",
    "matter_type": None,    # not set yet
    "draft_output": None,
    "messages": [],
    "error": None,
}

asyncio.run(demonstrate_rule2(test_state))
print("No crash — .get() handled None matter_type safely")


# ──────────────────────────────────────────────
# RULE 3: Return ONLY changed keys
# ──────────────────────────────────────────────
# WHY: If you return the full state, you OVERWRITE any keys set by previous nodes.
# Consider: intake sets "matter_type", then research sets "research_findings".
# If draft returns the full state (starting from the initial blank state), it
# would overwrite "research_findings" with None.
#
# Returning only changed keys lets LangGraph MERGE safely.

print("\n=== Rule 3: Return partial dict ===")

def simulate_langgraph_merge(state: dict, node_output: dict) -> dict:
    """LangGraph does this after each node (simplified)."""
    return {**state, **node_output}

state_after_intake = {
    "user_input": "draft a writ petition",
    "matter_type": "writ petition",   # set by intake
    "research_findings": None,
    "draft_output": None,
    "messages": [],
    "error": None,
}

state_after_research = simulate_langgraph_merge(state_after_intake, {
    "research_findings": [{"case": "AIR 1973 SC 1461"}]   # only keys that changed
})

# CORRECT draft node — only changes draft_output:
draft_output_correct = {"draft_output": "IN THE HIGH COURT..."}

# WRONG draft node — returns full state starting from initial blank:
draft_output_wrong = {
    "user_input": "draft a writ petition",
    "matter_type": "writ petition",
    "research_findings": None,      # ← DANGER: this would erase the findings!
    "draft_output": "IN THE HIGH COURT...",
    "messages": [],
    "error": None,
}

final_correct = simulate_langgraph_merge(state_after_research, draft_output_correct)
final_wrong = simulate_langgraph_merge(state_after_research, draft_output_wrong)

print(f"CORRECT: research_findings preserved: {final_correct['research_findings']}")
print(f"WRONG:   research_findings erased:    {final_wrong['research_findings']}")


# ──────────────────────────────────────────────
# RULE 4: NEVER raise — catch all, return error
# ──────────────────────────────────────────────
# WHY: If a node raises, LangGraph catches it and the graph CRASHES mid-run.
# The lawyer loses their progress.
# With {"error": str(e)}, the graph reaches END and the CLI shows the error message.
# The lawyer sees the error and can retry. Nothing is lost.

async def research_node_with_error_handling(state: LexState) -> dict:
    try:
        # In real code: call Indian Kanoon API
        # This might fail: network error, API key missing, rate limit, etc.
        raise ConnectionError("Indian Kanoon API is down")  # simulated failure

        return {"research_findings": [{"case": "AIR 1973 SC 1461"}]}

    except Exception as e:
        # NEVER raise — set error and return
        # The routing function will see state["error"] is set and route to END
        return {"error": str(e)}

print("\n=== Rule 4: Never raise — catch all ===")
result = asyncio.run(research_node_with_error_handling(test_state))
print(f"Error captured in state: {result}")  # {"error": "Indian Kanoon API is down"}
# The graph continues! END is reached cleanly. Lawyer sees the error message.


# ──────────────────────────────────────────────
# RULE 5: Never store state inside the node
# ──────────────────────────────────────────────
# WHY: Under concurrent Telegram usage, multiple requests run the same node
# simultaneously. If a node stores state in a module-level variable, requests
# will contaminate each other.
# Everything must live in the LexState dict.

# WRONG — state stored in module-level variable:
_cached_findings = []  # ← DANGER: shared across ALL concurrent requests

async def research_node_wrong(state: LexState) -> dict:
    global _cached_findings
    _cached_findings = [{"case": "AIR 1973 SC 1461"}]  # ← clobbers other requests
    return {"research_findings": _cached_findings}

# CORRECT — everything in state:
async def research_node_correct(state: LexState) -> dict:
    try:
        # All state comes from the state dict, all results go back through the return dict
        matter_type = state.get("matter_type") or "general"
        findings = [{"case": "AIR 1973 SC 1461", "for": matter_type}]
        return {"research_findings": findings}
    except Exception as e:
        return {"error": str(e)}

print("\n=== Rule 5: State lives in the dict, not the node ===")
print("Stateless nodes = safe concurrency = correct multi-user behavior")


# ──────────────────────────────────────────────
# PUTTING IT TOGETHER: A correct LexAgent-style node
# ──────────────────────────────────────────────

async def perfect_draft_node(state: LexState) -> dict:
    """
    This node follows all five rules.
    Compare this to the actual draft node in lexagent/nodes/draft.py.
    """
    try:
        # Rule 2: safe access
        matter_type = state.get("matter_type") or "general petition"
        messages = state.get("messages") or []

        # Do the work (in real code: await call_llm(...)):
        draft = f"[DRAFT] Court document for: {matter_type}"

        # Rule 3: return only changed keys
        return {
            "draft_output": draft,
            "messages": messages + [
                {"role": "assistant", "content": "Draft complete. Please review."}
            ],
        }
        # Rule 4: no raise — it's in the try block
        # Rule 5: no module-level variables touched

    except Exception as e:
        return {"error": str(e)}  # Rule 4: catch all, return error

print("\n=== A perfect LexAgent-style node ===")
state_with_type: LexState = {**test_state, "matter_type": "writ petition"}
result = asyncio.run(perfect_draft_node(state_with_type))
print(f"draft_output: {result['draft_output']}")
print(f"messages: {result['messages']}")


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# 1. If a node returns {"error": "..."}, what should the routing function do?
# 2. What happens if a node mutates state["messages"] in place vs. returning a new list?
# 3. Open lexagent/nodes/research.py and verify it follows all 5 rules.
#    Which rules are easiest to verify? Which require careful reading?

print("\n=== DONE — move on to 04_conditional_routing.py ===")
