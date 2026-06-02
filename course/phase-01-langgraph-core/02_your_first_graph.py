"""
02 — Your First StateGraph
===========================
Build and run a complete LangGraph graph from scratch.
No LLM calls — we stub everything so it runs instantly and for free.

Run this file:
    pip install langgraph langchain-core
    python 02_your_first_graph.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.graph import END, StateGraph

# ──────────────────────────────────────────────
# STEP 1: Define the State
# ──────────────────────────────────────────────
# Every graph needs a state TypedDict.
# Think of it as the "shared form" that all nodes read and write.

class SimpleMatterState(TypedDict):
    user_input: str
    matter_type: Optional[str]     # set by intake node
    draft_output: Optional[str]    # set by draft node
    messages: List[dict]
    error: Optional[str]

# ──────────────────────────────────────────────
# STEP 2: Define the Nodes
# ──────────────────────────────────────────────
# Each node is `async def run(state) -> dict`.
# The dict it returns is MERGED into the state — not a full replacement.

async def intake_node(state: SimpleMatterState) -> dict:
    """
    In real LexAgent: calls LLM to understand the matter brief,
    asks clarifying questions, extracts matter_type, parties, etc.

    Here: we stub it to always return "writ petition".
    """
    user_input = state.get("user_input", "")
    print(f"  [intake] processing: '{user_input}'")

    # Stub: in real code this would call an LLM
    detected_type = "writ petition"

    return {
        "matter_type": detected_type,
        "messages": state.get("messages", []) + [
            {"role": "assistant", "content": f"Understood. This is a {detected_type}."}
        ],
    }
    # CRITICAL: we return ONLY the keys we changed.
    # user_input, draft_output, error — we did not touch them, so they survive unchanged.


async def draft_node(state: SimpleMatterState) -> dict:
    """
    In real LexAgent: calls LLM with the matter type, parties, jurisdiction,
    case law findings, and skill instructions to generate a court-ready document.

    Here: we stub it to return a template.
    """
    matter_type = state.get("matter_type") or "general petition"
    print(f"  [draft] drafting a {matter_type}...")

    # Stub: in real code this would call an LLM
    draft = f"""IN THE HIGH COURT OF DELHI AT NEW DELHI

WRIT PETITION (CIVIL) NO. _____ OF 2024

IN THE MATTER OF:

Petitioner                          ...PETITIONER

VERSUS

Respondent                          ...RESPONDENT

WRIT PETITION UNDER ARTICLE 226 OF THE CONSTITUTION OF INDIA

[Generated for: {matter_type}]
"""

    return {
        "draft_output": draft,
        "messages": state.get("messages", []) + [
            {"role": "assistant", "content": "Draft complete. Review and finalize."}
        ],
    }


# ──────────────────────────────────────────────
# STEP 3: Define Routing Functions (for conditional edges)
# ──────────────────────────────────────────────
# A routing function receives the full state and returns a string.
# That string is the name of the next node, or END.

def route_after_intake(state: SimpleMatterState) -> str:
    """Decide what to do after intake runs."""
    if state.get("error"):
        return END
    if state.get("matter_type"):
        return "draft"    # intake successfully identified the matter type
    return END             # something went wrong


# ──────────────────────────────────────────────
# STEP 4: Build the Graph
# ──────────────────────────────────────────────

def build_simple_graph() -> StateGraph:
    """
    LANGGRAPH: StateGraph(SimpleMatterState) creates a typed graph.
    LangGraph uses the TypedDict to validate that nodes return valid keys.
    """
    graph = StateGraph(SimpleMatterState)

    # Register nodes — name maps to the function
    # LANGGRAPH: add_node(name, function) — the name is what routing returns to navigate here.
    graph.add_node("intake", intake_node)
    graph.add_node("draft", draft_node)

    # Set where every graph.invoke() call starts:
    # LANGGRAPH: set_entry_point(name) — every invocation begins here.
    graph.set_entry_point("intake")

    # Conditional edge: after intake, call route_after_intake to decide where to go:
    # LANGGRAPH: add_conditional_edges(source, routing_fn) — the routing function
    # receives the full state and returns a node name or END.
    graph.add_conditional_edges("intake", route_after_intake)

    # Fixed edge: after draft, always go to END:
    # LANGGRAPH: add_edge(source, target) — unconditional. Always routes here.
    graph.add_edge("draft", END)

    return graph


# ──────────────────────────────────────────────
# STEP 5: Compile and Run
# ──────────────────────────────────────────────
# The graph must be compiled before use.
# Compilation validates the graph structure (no dangling nodes, valid edges)
# and returns a runnable object.

async def main():
    print("=== Building graph ===")
    graph_def = build_simple_graph()

    # LANGGRAPH: compile() — validates and returns the runnable graph.
    # In LexAgent, compile() is called with a checkpointer (MemorySaver or Postgres).
    # Here we compile without one (no state persistence between calls).
    from langgraph.checkpoint.memory import MemorySaver
    graph = graph_def.compile(checkpointer=MemorySaver())

    # Initial state — this is what the CLI builds from the lawyer's input:
    initial_state: SimpleMatterState = {
        "user_input": "I need a writ petition challenging a government order",
        "matter_type": None,
        "draft_output": None,
        "messages": [],
        "error": None,
    }

    print("\n=== Running graph (method 1: ainvoke — waits for completion) ===")
    # LANGGRAPH: graph.ainvoke(state, config) — runs to END, returns final state.
    # config={"configurable": {"thread_id": "..."}} is required when using a checkpointer.
    final_state = await graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": "test-001"}},
    )
    print(f"matter_type: {final_state['matter_type']}")
    print(f"draft_output (first 100 chars): {final_state['draft_output'][:100]}...")
    print(f"messages count: {len(final_state['messages'])}")

    print("\n=== Running graph (method 2: astream — sees each node as it finishes) ===")
    # LANGGRAPH: graph.astream(state, config) — yields after each node finishes.
    # Each yielded value is a dict: {node_name: {keys_changed_by_this_node}}
    async for chunk in graph.astream(
        initial_state,
        config={"configurable": {"thread_id": "test-002"}},
    ):
        for node_name, node_output in chunk.items():
            keys = list(node_output.keys())
            print(f"  [node: {node_name}] changed keys: {keys}")


# ──────────────────────────────────────────────
# STEP 6: Understanding what compile() actually does
# ──────────────────────────────────────────────

print("""
WHAT compile() VALIDATES:
  ✓ Every node mentioned in add_edge/add_conditional_edges is registered
  ✓ There is an entry point
  ✓ Every node has at least one outgoing edge (or is END)
  ✓ No circular dependencies that would cause infinite loops

WHAT compile(checkpointer=...) ADDS:
  - A checkpointer saves a snapshot of LexState after each node
  - thread_id groups snapshots into "conversations"
  - Same thread_id on a second invoke() = resume from last checkpoint
  - This is how LexAgent "remembers" a matter across CLI sessions

In tests: compile(checkpointer=MemorySaver())  — fast, in-memory
In prod:  compile(checkpointer=AsyncPostgresSaver) — durable, survives restarts
""")

asyncio.run(main())
print("\n=== DONE — move on to 03_nodes_contract.py ===")
