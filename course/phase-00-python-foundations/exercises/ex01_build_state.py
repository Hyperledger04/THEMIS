"""
Exercise 01 — Build a Simplified LexState
==========================================
Your task: write a TypedDict called `MatterState` from scratch.

Requirements:
  - It must have at least 8 fields covering: input, intake, research, draft, and meta
  - Every intake field must be Optional (starts as None)
  - It must have a `messages` field of type List[dict]
  - It must have an `error` field of type Optional[str]
  - After defining it, create a valid initial state dict and print it

The goal is NOT to copy LexState. Design it yourself.
Then compare with lexagent/state.py and note the differences.

When done, answer in a comment at the bottom:
  1. Which fields did you name differently from LexState? Why?
  2. Which fields in the real LexState surprised you?
  3. What would you add if you were building this for a US court system?
"""

from typing import List, Optional, TypedDict

from lexagent.nodes import draft

# ──────────────────────────────────────────────
# YOUR TASK: Define MatterState below
# ──────────────────────────────────────────────
class MatterState(TypedDict):
    input : Optional[str]
    intake : Optional[str]
    research : Optional[str]
    draft : Optional[str]
    meta : Optional[dict]
    messages : List[dict]
    error : Optional[str]
    status : Optional[str]

print("MatterState defined with fields:")

state : MatterState ={
    "input" : "Brahm",
    "intake" : "Petition for writ of habeas corpus",
    "research" : None, 
    "draft" : None,
    "meta" : {"court": "Supreme Court", "jurisdiction": "Federal"},
    "messages" : [],
    "error" : None,
    "status" : "intake complete"
 }  

print(state["input"])
# class MatterState(TypedDict):
#     ...    ← fill this in

# ──────────────────────────────────────────────
# YOUR TASK: Create an initial state
# ──────────────────────────────────────────────

# initial: MatterState = {
#     ...    ← fill this in
# }

# ──────────────────────────────────────────────
# YOUR TASK: Simulate one node updating the state
# ──────────────────────────────────────────────
# Write a function that takes a MatterState and returns a partial dict
# (just the keys that changed — not the full state).
# The function should set the matter_type (or whatever you named it) to "writ petition".

# def after_intake(state: MatterState) -> dict:
#     ...

# ──────────────────────────────────────────────
# Verify your work
# ──────────────────────────────────────────────
# If you have defined everything above, uncomment and run these checks:

# result = after_intake(initial)
# print("Node output (partial dict):", result)
# merged = {**initial, **result}
# print("State after merge:", merged)

# ──────────────────────────────────────────────
# REFLECTION ANSWERS (fill in after completing)
# ──────────────────────────────────────────────
# 1. Fields I named differently:
# 2. Fields in real LexState that surprised me:
# 3. What I'd add for a US court system:
