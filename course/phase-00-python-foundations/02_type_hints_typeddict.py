"""
02 — Type Hints and TypedDict
==============================
This is the most important file in Phase 0 for understanding LexAgent.

LexAgent's entire state — everything the agent knows, has decided, and has produced —
lives in a single TypedDict called `LexState` in lexagent/state.py.

If you do not understand TypedDict, you cannot understand:
  - How the graph passes information between nodes
  - Why nodes return partial dicts instead of the full state
  - How LangGraph merges state updates

Run this file:
    python 02_type_hints_typeddict.py
"""

from typing import List, Optional, TypedDict

# ──────────────────────────────────────────────
# SECTION 1: What are type hints?
# ──────────────────────────────────────────────
# Python is dynamically typed — variables have no declared type.
# But you can ADD type hints (annotations) to tell readers (and tools) what to expect.
# Type hints do NOT enforce types at runtime — they are documentation + IDE help.

# Without type hints (valid Python, but hard to read):
def get_parties(matter):
    return matter["parties"]

# With type hints (same code, much clearer):
def get_parties_typed(matter: dict) -> dict:
    return matter["parties"]

# You can annotate local variables too:
case_name: str = "Kesavananda Bharati v State of Kerala"
citation: str = "AIR 1973 SC 1461"
is_supreme_court: bool = True
year: int = 1973

print("=== SECTION 1: Type hints ===")
print(f"{case_name} ({citation}), SC: {is_supreme_court}")


# ──────────────────────────────────────────────
# SECTION 2: Optional — the most common annotation in LexState
# ──────────────────────────────────────────────
# Optional[str] means "a str or None". It appears on almost every field in LexState
# because intake fields start as None and get filled as the agent asks questions.

# Old spelling (still works, still common in the codebase):
from typing import Optional as Opt
jurisdiction: Opt[str] = None       # not yet collected
matter_type: Opt[str] = None        # not yet collected

# New spelling (Python 3.10+, used in newer parts of LexAgent):
parties: str | None = None

# These two are identical:
# Optional[str]  ==  str | None
# You will see both in the codebase.

print("\n=== SECTION 2: Optional ===")
print(f"jurisdiction: {jurisdiction!r}")   # !r adds quotes around None
print(f"matter_type: {matter_type!r}")


# ──────────────────────────────────────────────
# SECTION 3: TypedDict — a dict with a schema
# ──────────────────────────────────────────────
# A regular dict has no schema — you can put anything in it.
# A TypedDict is a dict that has a defined set of keys and their types.
#
# WHY use TypedDict instead of a class?
#   - LangGraph works with plain dicts under the hood
#   - TypedDict gives you IDE autocomplete and type checking
#   - You still get dict.get(), dict["key"], etc.
#   - No OOP boilerplate — no __init__, no self, no methods needed

class SimpleState(TypedDict):
    """A minimal example TypedDict to understand the pattern."""
    user_input: str                   # required — always present
    matter_type: Optional[str]        # optional — might be None
    intake_complete: bool             # required — always present
    messages: List[dict]              # required — always a list (starts empty)

# Creating a SimpleState value — it's just a dict that matches the schema:
state: SimpleState = {
    "user_input": "I need a writ petition",
    "matter_type": None,              # not collected yet
    "intake_complete": False,
    "messages": [],
}

print("\n=== SECTION 3: TypedDict ===")
print(f"user_input: {state['user_input']}")
print(f"matter_type: {state.get('matter_type', 'not set')}")
print(f"intake_complete: {state['intake_complete']}")


# ──────────────────────────────────────────────
# SECTION 4: How nodes update state — the key insight
# ──────────────────────────────────────────────
# LangGraph nodes do NOT return the full state.
# They return ONLY the keys they changed.
# LangGraph merges the partial dict into the existing state.
#
# WHY: If every node returned the full state, you would lose information
# added by previous nodes. With partial returns, each node adds its
# contribution without clobbering everyone else's work.

def simulate_node_merge(state: dict, node_output: dict) -> dict:
    """
    This is roughly what LangGraph does internally after each node runs.
    It merges the partial output into the current state.
    (The real version is more sophisticated for lists, but this shows the idea.)
    """
    return {**state, **node_output}

# Initial state (what we start with):
initial_state = {
    "user_input": "I need a writ petition",
    "matter_type": None,
    "jurisdiction": None,
    "intake_complete": False,
    "messages": [],
}

print("\n=== SECTION 4: How nodes update state ===")
print("Before intake node:", initial_state)

# Intake node runs and returns ONLY the keys it changed:
intake_output = {
    "matter_type": "writ petition",
    "jurisdiction": "Delhi High Court",
    "messages": [{"role": "assistant", "content": "What is the fundamental right at stake?"}],
}

# LangGraph merges:
after_intake = simulate_node_merge(initial_state, intake_output)
print("\nAfter intake node:", after_intake)
# Notice: user_input is still there! intake_output didn't include it, but it survived.


# ──────────────────────────────────────────────
# SECTION 5: LexState — the real thing
# ──────────────────────────────────────────────
# Let's look at the actual LexState TypedDict from lexagent/state.py.
# I'll show a simplified version here so you can see the structure.

class LexStateSimplified(TypedDict):
    """
    A simplified version of LexState showing the key phases.
    The real LexState has ~50 fields — one for each piece of information
    the agent collects, decides, or produces.
    """

    # ── INTAKE phase fields (collected by asking the lawyer questions) ──
    user_input: str
    matter_id: Optional[str]
    matter_type: Optional[str]
    parties: Optional[dict]
    jurisdiction: Optional[str]
    purpose: Optional[str]
    intake_complete: bool

    # ── RESEARCH phase fields (produced by the research node) ──
    research_findings: Optional[List[dict]]   # [{case_name, citation, relevance, url}]
    statutes_cited: Optional[List[str]]

    # ── DRAFT phase fields (produced by the draft node) ──
    draft_output: Optional[str]
    plain_english_summary: Optional[str]

    # ── CITATION phase fields (produced by the cite node) ──
    citations_verified: bool
    unverified_citations: Optional[List[str]]

    # ── META fields (used across the whole graph) ──
    messages: List[dict]          # full conversation history
    lawyer_soul: Optional[dict]   # lawyer's preferences from SOUL.md
    error: Optional[str]          # any error — nodes catch and set this

# A valid LexStateSimplified value:
example_state: LexStateSimplified = {
    "user_input": "Draft a writ petition for my client",
    "matter_id": "M-20240501-001",
    "matter_type": None,              # intake hasn't run yet
    "parties": None,
    "jurisdiction": None,
    "purpose": None,
    "intake_complete": False,
    "research_findings": None,
    "statutes_cited": None,
    "draft_output": None,
    "plain_english_summary": None,
    "citations_verified": False,
    "unverified_citations": None,
    "messages": [],
    "lawyer_soul": None,
    "error": None,
}

print("\n=== SECTION 5: LexState structure ===")
print(f"Intake complete: {example_state['intake_complete']}")
print(f"Draft ready: {example_state['draft_output'] is not None}")
print(f"Error: {example_state.get('error')}")


# ──────────────────────────────────────────────
# SECTION 6: State.get() vs State[] — why LexAgent uses .get()
# ──────────────────────────────────────────────
# Both access dict values. The difference matters:
#   state["key"]          → raises KeyError if key doesn't exist
#   state.get("key")      → returns None if key doesn't exist
#   state.get("key", "X") → returns "X" if key doesn't exist

# In LexAgent nodes, you almost always see:
#   findings = state.get("research_findings") or []
#
# Breaking that down:
#   1. state.get("research_findings") → None if not set
#   2. None or []  → [] (because None is falsy)
# Result: safe default of empty list when findings haven't been collected yet.

findings = example_state.get("research_findings") or []
statutes = example_state.get("statutes_cited") or []
print("\n=== SECTION 6: .get() pattern ===")
print(f"findings (safe): {findings}")        # [] — not None
print(f"statutes (safe): {statutes}")        # [] — not None


# ──────────────────────────────────────────────
# PAUSE AND THINK
# ──────────────────────────────────────────────
# Before moving to 03_async_await.py:
#
# 1. What is the difference between a TypedDict and a regular dict?
# 2. Why do nodes return partial dicts instead of the full state?
# 3. What does Optional[str] mean?
# 4. Why does LexAgent use `state.get("key") or []` instead of `state["key"]`?
# 5. Open lexagent/state.py in the repo and find three fields you can now explain.
#
# When you can answer all five, move on.

print("\n=== DONE — move on to 03_async_await.py ===")
