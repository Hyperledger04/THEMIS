"""
06 — Checkpointers: Persistence Across Sessions
================================================
A checkpointer is what lets LexAgent "remember" a matter across CLI sessions.
Without one, every `lex draft "..."` command starts from scratch.
With one, the lawyer can resume a matter tomorrow from where they left off.

This file teaches:
  - What a checkpointer does (saves state after every node)
  - MemorySaver (fast, in-memory, for tests and CLI)
  - AsyncPostgresSaver (durable, for production)
  - thread_id — the key that links invocations into a "conversation"

Run this file:
    python 06_checkpointers.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


class MatterState(TypedDict):
    user_input: str
    matter_type: Optional[str]
    draft_output: Optional[str]
    step_count: int    # track how many times nodes have run
    messages: List[dict]
    error: Optional[str]


async def intake_node(state: MatterState) -> dict:
    count = state.get("step_count", 0) + 1
    print(f"  [intake] run #{count}")
    return {"matter_type": "writ petition", "step_count": count}

async def draft_node(state: MatterState) -> dict:
    count = state.get("step_count", 0) + 1
    print(f"  [draft] run #{count}, matter: {state.get('matter_type')}")
    return {"draft_output": "[DRAFT COMPLETE]", "step_count": count}


def build_graph():
    g = StateGraph(MatterState)
    g.add_node("intake", intake_node)
    g.add_node("draft", draft_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "draft")
    g.add_edge("draft", END)
    return g


# ──────────────────────────────────────────────
# CONCEPT 1: What a checkpointer does
# ──────────────────────────────────────────────

print("""
WHAT A CHECKPOINTER DOES:

After every node runs, the checkpointer saves a SNAPSHOT of the full LexState.
Each snapshot is tagged with (thread_id, checkpoint_id).

Timeline for a single matter:
  invoke #1 → intake runs  → snapshot saved (thread="matter-001", cp=1)
  invoke #1 → draft runs   → snapshot saved (thread="matter-001", cp=2)

  [lawyer closes laptop, comes back tomorrow]

  invoke #2 (same thread_id="matter-001") → LangGraph loads cp=2
            → graph sees the existing state, picks up where it left off

WITHOUT a checkpointer: every invoke is a fresh start. State is lost.
WITH a checkpointer:    same thread_id = same conversation. State persists.
""")


# ──────────────────────────────────────────────
# CONCEPT 2: MemorySaver — the in-process checkpointer
# ──────────────────────────────────────────────
# MemorySaver stores checkpoints in a dict in the current Python process.
# Fast (no I/O), safe for tests, but state is lost when the process exits.
# Used in: pytest tests, CLI single-session runs, development

async def demo_memory_saver():
    print("\n=== MemorySaver: state lives only in this process ===")

    graph_def = build_graph()

    # LANGGRAPH: MemorySaver stores all checkpoints in a dict in RAM.
    # Creating a new MemorySaver() instance starts fresh — no previous state.
    checkpointer = MemorySaver()
    graph = graph_def.compile(checkpointer=checkpointer)

    thread_id = "test-matter-001"
    config = {"configurable": {"thread_id": thread_id}}

    initial: MatterState = {
        "user_input": "draft writ petition",
        "matter_type": None,
        "draft_output": None,
        "step_count": 0,
        "messages": [],
        "error": None,
    }

    # First invocation:
    result1 = await graph.ainvoke(initial, config=config)
    print(f"After invoke #1: step_count={result1['step_count']}, draft={result1['draft_output']}")

    # Same thread — LangGraph detects the final state was already reached.
    # A new invoke continues from the last checkpoint.
    # (In this simple graph, both nodes already ran, so no new nodes will run.)
    result2 = await graph.ainvoke(initial, config=config)
    print(f"After invoke #2 (same thread): step_count={result2['step_count']}")
    print(f"  → Note: same step_count — graph resumed from checkpoint, didn't re-run nodes")

asyncio.run(demo_memory_saver())


# ──────────────────────────────────────────────
# CONCEPT 3: thread_id — the conversation key
# ──────────────────────────────────────────────
# thread_id groups all checkpoints for one "conversation" (one matter).
# Different thread_id = completely separate state — different matter.
# Same thread_id = resume this matter.
#
# In LexAgent:
#   thread_id = matter_id (e.g., "M-20240501-001")
# In Telegram:
#   thread_id = str(telegram_user_id)  (one thread per user)
# In tests:
#   thread_id = uuid4() (fresh thread per test to avoid cross-contamination)

async def demo_thread_isolation():
    print("\n=== thread_id isolates matters from each other ===")

    graph_def = build_graph()
    checkpointer = MemorySaver()
    graph = graph_def.compile(checkpointer=checkpointer)

    initial: MatterState = {
        "user_input": "x", "matter_type": None, "draft_output": None,
        "step_count": 0, "messages": [], "error": None,
    }

    # Two separate matters — different thread IDs:
    result_a = await graph.ainvoke(initial, config={"configurable": {"thread_id": "matter-sharma"}})
    result_b = await graph.ainvoke(initial, config={"configurable": {"thread_id": "matter-mehta"}})

    print(f"matter-sharma: step_count={result_a['step_count']}")
    print(f"matter-mehta:  step_count={result_b['step_count']}")
    print("Both ran independently — different thread_ids = completely separate")

asyncio.run(demo_thread_isolation())


# ──────────────────────────────────────────────
# CONCEPT 4: AsyncPostgresSaver — the production checkpointer
# ──────────────────────────────────────────────
# For production, LexAgent uses Postgres for durable state.
# State survives process restarts, server crashes, and deployments.
#
# To use it:
#   pip install langgraph-checkpoint-postgres
#   DATABASE_URL=postgresql://... in .env
#
# In lexagent/graph.py:
#
#   if cfg.postgres_url:
#       from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
#       checkpointer = AsyncPostgresSaver.from_conn_string(cfg.postgres_url)
#       return graph_def.compile(checkpointer=checkpointer)
#   else:
#       from langgraph.checkpoint.memory import MemorySaver
#       return graph_def.compile(checkpointer=MemorySaver())
#
# This is exactly the fallback pattern in _build_with_checkpointer().

print("""
=== AsyncPostgresSaver: durable production persistence ===

Tables LangGraph creates in Postgres:
  checkpoints         — one row per checkpoint (thread_id, checkpoint_id, state)
  checkpoint_blobs    — large state chunks (binary storage)
  checkpoint_writes   — partial writes during node execution

To set up:
  1. Start Postgres (docker or cloud)
  2. Set DATABASE_URL in .env
  3. Call await setup_checkpointer() once on server startup (creates tables)
  4. Use get_graph(cfg) — it automatically uses Postgres when DATABASE_URL is set

WHY bother? Three superpowers:
  1. Time travel: restore any checkpoint and re-run from there (debugging)
  2. Human-in-the-loop: interrupt at any node, modify state, resume
  3. Fault tolerance: if the server crashes mid-draft, the next invoke resumes
""")


# ──────────────────────────────────────────────
# CONCEPT 5: The graph singleton in LexAgent
# ──────────────────────────────────────────────
# Building and compiling the graph takes ~50ms.
# Under concurrent Telegram traffic, you don't want to rebuild it per request.
# LexAgent builds it ONCE and caches it in a module-level dict.
#
# From lexagent/graph.py:
#
#   _GRAPHS: dict = {}    # keyed by "postgres" or "memory"
#
#   def get_graph(cfg=None):
#       key = "postgres" if cfg.postgres_url else "memory"
#       if key in _GRAPHS:
#           return _GRAPHS[key]
#       _GRAPHS[key] = _build_with_checkpointer(cfg)
#       return _GRAPHS[key]
#
# Any code that needs the graph calls: graph = get_graph()
# It is built once on first call, then served from cache on every subsequent call.

print("""
=== Graph singleton pattern ===

In the real codebase (lexagent/graph.py):

  _GRAPHS = {}  # module-level cache — survives across function calls

  def get_graph(cfg=None):
      key = "postgres" if cfg.postgres_url else "memory"
      if key in _GRAPHS:
          return _GRAPHS[key]    # return cached — no rebuild
      _GRAPHS[key] = _build_with_checkpointer(cfg)
      return _GRAPHS[key]

  # In tests that need a fresh graph:
  def invalidate_graph_cache():
      global _GRAPHS
      _GRAPHS.clear()

WHY: Building the graph is fast but not free. Under concurrent requests,
rebuilding per-request is wasteful. The singleton is thread-safe in Python
because the GIL ensures module-level dict mutations are atomic.
""")


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# 1. What is the difference between MemorySaver and AsyncPostgresSaver?
#    When would you use each?
# 2. Why does LexAgent use a matter_id as the thread_id?
# 3. What happens if two requests use the same thread_id at the same time?
# 4. Open lexagent/graph.py, find _build_with_checkpointer().
#    Trace exactly what happens when cfg.postgres_url is None.
# 5. Why does invalidate_graph_cache() exist? (Hint: look at the test files)

print("\n=== PHASE 1 COMPLETE ===")
print("You can now read lexagent/graph.py and understand every line.")
print("You know: StateGraph, nodes, edges, conditional routing, human-in-the-loop, checkpointers.")
print("Move on to phase-02-memory/ when ready.")
