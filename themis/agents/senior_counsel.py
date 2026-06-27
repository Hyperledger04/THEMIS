# Senior Counsel subgraph — the orchestration layer of V3.3.
#
# Graph flow:
#   intake → plan_node → coordinate → [send() to specialist] → coordinate → ... → persist_matter_step → END
#                      ↘ contract_review → END   (existing branch, unchanged)
#
# LANGGRAPH: send() dispatch — coordinate's conditional edge returns [Send("run_X", state)].
# After the specialist node completes, its outgoing edge loops back to coordinate.
# coordinate re-evaluates execution_plan[0] for the next specialist.
# When the plan is empty → route to persist_matter_step → END.
#
# WHY Senior Counsel owns persist_matter():
#   Single writer prevents race conditions when Lavern multi-agent (Phase 11) adds
#   67 parallel agents. Specialists never call Postgres directly (Key Invariant §1).

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from themis.agents import drafter, researcher, reviewer, verification
from themis.agents.profiles import SPECIALIST_WHITELIST, plan_for_matter
from themis.nodes import contract_review, intake
from themis.state import SeniorCounselState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Specialist node name → callable mapping
# WHY: string-keyed dict makes SPECIALIST_WHITELIST enforcement trivial —
# if the name is not in this dict, the graph has no such node.
# ---------------------------------------------------------------------------
_SPECIALIST_NODES: dict[str, object] = {
    "researcher":   researcher.run,
    "drafter":      drafter.run,
    "reviewer":     reviewer.run,
    "verification": verification.run,
}

# ---------------------------------------------------------------------------
# Plan node — creates execution_plan from matter_type
# ---------------------------------------------------------------------------

async def plan_node(state: SeniorCounselState) -> dict:
    """
    Translate matter_type + flags into an ordered execution_plan.
    Senior Counsel is the only agent that reads matter_type to create the plan.
    Specialists never inspect matter_type to decide what to do next — that is
    Senior Counsel's role.
    """
    mt = state.get("matter_type") or ""
    research_only = bool(state.get("research_only"))
    plan = plan_for_matter(mt, research_only=research_only)

    logger.info("Senior Counsel plan for '%s': %s", mt, [s["specialist"] for s in plan])

    return {
        "execution_plan": plan,
        "active_specialist": None,
        "status": "researching" if plan else "complete",
    }


# ---------------------------------------------------------------------------
# Coordinate node — no-op hub; routing logic lives in route_after_coordinate()
# ---------------------------------------------------------------------------

async def coordinate(state: SeniorCounselState) -> dict:
    """
    No-op coordination node. Its outgoing conditional edge (route_after_coordinate)
    does the actual dispatch via send() or routes to persist_matter_step.
    WHY no-op: keeping state mutation out of routing functions keeps the graph
    deterministic and easy to test — routing functions should be pure.
    """
    return {}


# ---------------------------------------------------------------------------
# Persist matter node — syncs final state to Postgres
# ---------------------------------------------------------------------------

async def persist_matter_step(state: SeniorCounselState) -> dict:
    """
    Sync the completed matter state to Postgres via MatterStore.persist_matter().
    Skips gracefully when no postgres_url is configured (dev / CI mode).

    WHY only Senior Counsel calls this: single writer prevents race conditions
    when multiple specialist agents run concurrently (Phase 11).
    """
    try:
        from themis.config import LexConfig
        cfg = LexConfig()

        if not cfg.postgres_url:
            logger.debug("persist_matter_step: no postgres_url — skipping Postgres sync")
            return {"status": "complete"}

        from themis.db.matter_store import MatterStore
        store = MatterStore(cfg.postgres_url)
        await store.persist_matter(dict(state))
        logger.info("Senior Counsel: matter %s persisted to Postgres", state.get("matter_id"))
        return {"status": "complete"}

    except Exception as e:
        # WHY: persist failure is not fatal — the in-memory state is still correct.
        # Log the error and continue so the lawyer gets their draft even if DB is down.
        logger.warning("persist_matter_step failed (non-fatal): %s", e)
        return {"status": "complete", "error": f"persist_matter: {e}"}


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

# Matter types that skip research (same list as old graph.py)
_NO_RESEARCH_TYPES = (
    "legal notice",
    "demand notice",
    "affidavit",
    "vakalatnama",
)


def route_after_intake(state: SeniorCounselState) -> str:
    """
    After intake: loop back to END (CLI re-invokes) if incomplete.
    On completion, contract_review routes directly; everything else goes to plan_node.
    """
    if state.get("error"):
        return END

    if state.get("intake_complete"):
        if state.get("workflow_mode") == "contract_review":
            return "contract_review"
        return "plan_node"

    # WHY END (not "intake"): see original graph.py — this gives CLI control back
    # so the user's answers can be injected before the next invocation.
    return END


def route_after_coordinate(state: SeniorCounselState) -> list | str:
    """
    LANGGRAPH: Returns either [Send("run_X", state)] to dispatch the next specialist
    or "persist_matter_step" when the execution_plan is exhausted.

    WHY send() not a simple conditional edge: send() lets Senior Counsel pass a
    scoped state to each specialist. In R1, ResearcherState (not full SeniorCounselState)
    will flow into the researcher subgraph — the boundary is established here in V3.3.
    """
    if state.get("error"):
        return END

    plan = state.get("execution_plan") or []
    if not plan:
        return "persist_matter_step"

    specialist = plan[0].get("specialist", "")

    # Whitelist check — block hallucinated specialist names
    if specialist not in SPECIALIST_WHITELIST:
        logger.error("Blocked unknown specialist '%s' (not in whitelist)", specialist)
        return "persist_matter_step"

    node_name = f"run_{specialist}"
    logger.info("Senior Counsel dispatching → %s", node_name)

    # LANGGRAPH: Send(node_name, state) routes the graph to node_name with state as input.
    # After node_name completes, the graph follows node_name's outgoing edge (→ coordinate).
    return [Send(node_name, state)]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_senior_counsel_graph() -> StateGraph:
    """
    Assemble the Senior Counsel StateGraph (without checkpointer).

    LANGGRAPH: Returns an uncompiled StateGraph. Call .compile() with the
    appropriate checkpointer at graph.py startup time.

    Node layout:
        intake → plan_node → coordinate
        coordinate → (conditional) → [Send(run_X)] → coordinate → … → persist_matter_step → END
        intake → (conditional, contract_review path) → contract_review → END
    """
    graph = StateGraph(SeniorCounselState)

    # Core Senior Counsel nodes
    graph.add_node("intake", intake.run)
    graph.add_node("plan_node", plan_node)
    graph.add_node("coordinate", coordinate)
    graph.add_node("persist_matter_step", persist_matter_step)

    # Specialist runner nodes — each wraps its agent and loops back to coordinate
    # LANGGRAPH: add_conditional_edges from each run_X → coordinate creates the loop
    for name, fn in _SPECIALIST_NODES.items():
        node_id = f"run_{name}"
        graph.add_node(node_id, fn)
        graph.add_edge(node_id, "coordinate")   # loop back after specialist completes

    # Contract review branch (existing node, unchanged interface)
    graph.add_node("contract_review", contract_review.run)
    graph.add_edge("contract_review", END)

    # Terminal
    graph.add_edge("persist_matter_step", END)

    # Entry point
    graph.set_entry_point("intake")

    # Intake → plan_node or contract_review or END (human-in-the-loop)
    graph.add_conditional_edges("intake", route_after_intake)

    # plan_node → coordinate (always)
    graph.add_edge("plan_node", "coordinate")

    # LANGGRAPH: add_conditional_edges from coordinate dispatches specialists via send()
    # or routes to persist_matter_step when the plan is exhausted.
    graph.add_conditional_edges("coordinate", route_after_coordinate)

    return graph
