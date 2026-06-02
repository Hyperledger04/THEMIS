"""
04 — Conditional Routing
=========================
The real power of LangGraph is conditional edges — they let the graph
make decisions based on state values.

This file teaches:
  - How routing functions work
  - The exact routing logic from lexagent/graph.py
  - How to add a new branch to the graph

Run this file:
    python 04_conditional_routing.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

# ──────────────────────────────────────────────
# STATE
# ──────────────────────────────────────────────

class MatterState(TypedDict):
    user_input: str
    matter_type: Optional[str]
    intake_complete: bool
    research_findings: Optional[List[dict]]
    research_only: Optional[bool]
    draft_output: Optional[str]
    workflow_mode: Optional[str]    # "draft" | "contract_review"
    messages: List[dict]
    error: Optional[str]

# ──────────────────────────────────────────────
# ROUTING FUNCTIONS — the decision points
# ──────────────────────────────────────────────
# These are pure functions: they take state, return a string.
# No I/O, no async, no side effects.

# Matter types that skip research (no case law needed):
_NO_RESEARCH_TYPES = ("legal notice", "demand notice", "affidavit", "vakalatnama")

def route_after_intake(state: MatterState) -> str:
    """
    This is the exact routing logic from lexagent/graph.py.
    After intake runs, decide: keep collecting info? research? draft directly?
    """
    if state.get("error"):
        return END

    if state.get("intake_complete"):
        # Contract review is a separate branch:
        if state.get("workflow_mode") == "contract_review":
            return "contract_review"

        # Some document types don't need case law:
        mt = (state.get("matter_type") or "").lower()
        if any(t in mt for t in _NO_RESEARCH_TYPES):
            print(f"  [router] '{mt}' → skipping research, going direct to draft")
            return "draft"

        return "research"

    # Intake is not complete — stop the graph and let the CLI ask questions:
    print(f"  [router] intake not complete → END (CLI will ask more questions)")
    return END


def route_after_research(state: MatterState) -> str:
    """After research: either draft, or stop if this was a research-only request."""
    if state.get("error"):
        return END
    if state.get("research_only"):
        print("  [router] research_only=True → END (show findings, no draft)")
        return END
    return "draft"


def route_after_draft(state: MatterState) -> str:
    """After draft: verify citations if we have findings to check against."""
    if state.get("error"):
        return END
    if state.get("research_findings"):
        return "cite"
    return "review"   # no findings to verify against — skip straight to review


# ──────────────────────────────────────────────
# NODES (stubbed — no real LLM)
# ──────────────────────────────────────────────

async def intake_node(state: MatterState) -> dict:
    user_input = state.get("user_input", "")
    print(f"  [intake] analyzing: '{user_input}'")

    # Simulate: detect matter type from user input
    if "writ" in user_input.lower():
        return {"matter_type": "writ petition", "intake_complete": True}
    elif "notice" in user_input.lower():
        return {"matter_type": "legal notice", "intake_complete": True}
    elif "contract" in user_input.lower():
        return {"matter_type": "contract review", "intake_complete": True,
                "workflow_mode": "contract_review"}
    else:
        # Not complete — need more info
        return {
            "messages": state.get("messages", []) + [
                {"role": "assistant", "content": "What type of document do you need?"}
            ]
        }

async def research_node(state: MatterState) -> dict:
    print(f"  [research] searching case law for: {state.get('matter_type')}")
    return {
        "research_findings": [
            {"case": "Kesavananda Bharati", "citation": "AIR 1973 SC 1461"},
            {"case": "Maneka Gandhi", "citation": "AIR 1978 SC 597"},
        ]
    }

async def draft_node(state: MatterState) -> dict:
    matter_type = state.get("matter_type")
    findings_count = len(state.get("research_findings") or [])
    print(f"  [draft] writing {matter_type} (using {findings_count} findings)")
    return {"draft_output": f"[DRAFT] {matter_type} with {findings_count} case references"}

async def cite_node(state: MatterState) -> dict:
    draft = state.get("draft_output") or ""
    print(f"  [cite] verifying citations in draft ({len(draft)} chars)")
    return {"citations_verified": True}

async def review_node(state: MatterState) -> dict:
    print(f"  [review] final validation complete")
    return {}   # no state changes — just marks the matter as reviewed

async def contract_review_node(state: MatterState) -> dict:
    print(f"  [contract_review] analyzing contract for risks")
    return {"draft_output": "[CONTRACT REVIEW REPORT] Risk level: MEDIUM"}

# ──────────────────────────────────────────────
# BUILD THE GRAPH
# ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(MatterState)

    graph.add_node("intake", intake_node)
    graph.add_node("research", research_node)
    graph.add_node("draft", draft_node)
    graph.add_node("cite", cite_node)
    graph.add_node("review", review_node)
    graph.add_node("contract_review", contract_review_node)

    graph.set_entry_point("intake")

    graph.add_conditional_edges("intake", route_after_intake)
    graph.add_conditional_edges("research", route_after_research)
    graph.add_conditional_edges("draft", route_after_draft)

    graph.add_edge("cite", "review")
    graph.add_edge("review", END)
    graph.add_edge("contract_review", END)

    return graph


# ──────────────────────────────────────────────
# RUN: Three different request types
# ──────────────────────────────────────────────

async def run_scenario(label: str, user_input: str, research_only: bool = False):
    print(f"\n{'='*60}")
    print(f"SCENARIO: {label}")
    print(f"Input: '{user_input}'")
    print(f"{'='*60}")

    graph_def = build_graph()
    graph = graph_def.compile(checkpointer=MemorySaver())

    initial: MatterState = {
        "user_input": user_input,
        "matter_type": None,
        "intake_complete": False,
        "research_findings": None,
        "research_only": research_only,
        "draft_output": None,
        "workflow_mode": None,
        "messages": [],
        "error": None,
    }

    import uuid
    thread_id = str(uuid.uuid4())

    async for chunk in graph.astream(initial, config={"configurable": {"thread_id": thread_id}}):
        for node_name, _ in chunk.items():
            pass   # router output already printed inside each node

    # Get final state by running invoke on a fresh thread:
    final = await graph.ainvoke(initial, config={"configurable": {"thread_id": str(uuid.uuid4())}})
    print(f"RESULT:")
    print(f"  matter_type: {final.get('matter_type')}")
    print(f"  draft_output: {final.get('draft_output')}")
    print(f"  findings: {len(final.get('research_findings') or [])}")


async def main():
    # Scenario 1: writ petition — full pipeline (research → draft → cite → review)
    await run_scenario(
        "Writ petition — full pipeline",
        "I need a writ petition challenging a government order"
    )

    # Scenario 2: legal notice — skips research (router detects notice type)
    await run_scenario(
        "Legal notice — skips research",
        "I need a legal notice for payment default"
    )

    # Scenario 3: contract review — separate branch
    await run_scenario(
        "Contract review — separate branch",
        "Please review this contract for risks"
    )


# ──────────────────────────────────────────────
# KEY INSIGHT: The routing function IS the business logic
# ──────────────────────────────────────────────

print("""
KEY INSIGHT:
  The routing functions in lexagent/graph.py encode most of LexAgent's
  business logic:

  - "Should we research?" → route_after_intake checks matter_type
  - "Should we verify citations?" → route_after_draft checks research_findings
  - "Should we stop for human input?" → route_after_intake checks intake_complete

  When you need to add a new feature (e.g., "add a hearing scheduler step"),
  you add a new node and update the routing function.
  The nodes themselves don't need to know about each other.
""")

asyncio.run(main())
print("\n=== DONE — move on to 05_human_in_the_loop.py ===")
