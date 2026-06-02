"""
Exercise 01 — Build a 2-Node Agent: Intake → Draft
====================================================
Build a working LangGraph agent from scratch without copying from the examples.

Requirements:
  1. Define a state TypedDict with at least 6 fields
  2. Write an intake_node that:
     - Detects the matter type from user_input
     - Returns a question if matter_type is not clear
     - Sets intake_complete=True when it has enough info
  3. Write a draft_node that:
     - Uses the matter_type, jurisdiction, and purpose from state
     - Returns a draft_output string
  4. Write a routing function that:
     - Goes to "draft" when intake_complete=True
     - Returns END otherwise
  5. Build the graph and compile it with MemorySaver
  6. Run it with a simulated 2-turn conversation (one question/answer)

Test cases to pass before moving on:
  - Invoke with "writ petition against eviction" → gets a draft in 1-2 turns
  - Invoke with "help with legal matter" → asks a question before drafting

pip install langgraph langchain-core
python ex01_build_intake_draft.py
"""

import asyncio
from typing import List, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

# ──────────────────────────────────────────────
# YOUR TASK: Define state, nodes, routing, graph
# ──────────────────────────────────────────────

# 1. State:
# class MatterState(TypedDict):
#     ...

# 2. Intake node:
# async def intake_node(state: MatterState) -> dict:
#     ...

# 3. Draft node:
# async def draft_node(state: MatterState) -> dict:
#     ...

# 4. Routing:
# def route_after_intake(state: MatterState) -> str:
#     ...

# 5. Graph:
# def build_graph():
#     ...

# 6. Main:
# async def main():
#     ...
#     # Test case 1: clear brief
#     # Test case 2: vague brief — should ask a question first

# asyncio.run(main())

# ──────────────────────────────────────────────
# REFLECTION (fill in after completing)
# ──────────────────────────────────────────────
# 1. What did you find hardest to get right?
# 2. What would you need to add to make intake handle 3 questions (not just 1)?
# 3. Open lexagent/nodes/intake.py. What does the real intake do that yours doesn't?
