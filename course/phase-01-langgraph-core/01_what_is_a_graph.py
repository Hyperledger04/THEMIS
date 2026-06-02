"""
01 — What Is a StateGraph?
===========================
Before writing any code, you need a clear mental model of what LangGraph is.
This file builds that model with analogies and diagrams.

No code to run here — just read it carefully.
"""

# ──────────────────────────────────────────────
# THE CORE ANALOGY: A workflow with shared memory
# ──────────────────────────────────────────────
#
# Imagine you hire three paralegals to process a legal matter:
#
#   Paralegal 1 (Intake)     — talks to the client, fills in a form
#   Paralegal 2 (Research)   — searches case law, fills in the form
#   Paralegal 3 (Drafting)   — reads the form, writes the document
#
# There is ONE form on the table. Each paralegal:
#   - Reads the relevant fields
#   - Does their work
#   - Writes their results back to the form
#   - Passes the form to the next paralegal
#
# Nobody keeps anything in their head. Everything is on the form.
# If any paralegal makes a mistake, you can rewind by restoring the form.
#
# In LangGraph:
#   "the form"       = LexState (a TypedDict)
#   "paralegals"     = nodes (async def functions)
#   "the office"     = StateGraph
#   "who goes next"  = edges (fixed) or conditional edges (routing functions)

print("""
MENTAL MODEL: LexAgent as a paralegal office
=============================================
                     ┌──────────────────────────────┐
                     │          LexState             │
                     │  (the shared form on the      │
                     │   table — everyone reads      │
                     │   and writes here)            │
                     └──────────────────────────────┘
                            ▲         ▲         ▲
                            │         │         │
                    reads/  │         │         │  reads/
                    writes  │         │         │  writes
                            │         │         │
                         [intake]  [research]  [draft]
                         node      node        node
""")

# ──────────────────────────────────────────────
# THREE TYPES OF CONNECTIONS IN A GRAPH
# ──────────────────────────────────────────────

print("""
TYPE 1: Fixed edge — always go to this node next
  graph.add_edge("cite", "review")
  → after cite runs, ALWAYS run review

TYPE 2: Conditional edge — decide based on state
  graph.add_conditional_edges("intake", route_after_intake)
  → after intake runs, call route_after_intake(state) to decide

TYPE 3: Entry point — where every graph run starts
  graph.set_entry_point("intake")
  → every call to graph.invoke() starts at intake
""")

# ──────────────────────────────────────────────
# THE ROUTING FUNCTION — how conditional edges work
# ──────────────────────────────────────────────

print("""
A ROUTING FUNCTION (from lexagent/graph.py):

    def route_after_intake(state: LexState) -> str:
        if state.get("error"):
            return END            # something went wrong — stop
        if state.get("intake_complete"):
            return "research"     # lawyer answered all questions — go to research
        return END                # lawyer needs to answer more — stop and wait

    graph.add_conditional_edges("intake", route_after_intake)

WHY return END instead of looping back to intake?
  - If we looped back, the LLM would ask another question with no new user input.
  - That creates an infinite spinner with no visible output.
  - Instead, we return END (stop), show the question in the CLI,
    wait for the lawyer's answer, then RE-INVOKE the graph with the answer.
  - This is the "human-in-the-loop" pattern — the graph pauses for human input.
""")

# ──────────────────────────────────────────────
# HOW INVOKE WORKS vs STREAM
# ──────────────────────────────────────────────

print("""
TWO WAYS TO RUN A GRAPH:

1. graph.invoke(initial_state)
   - Runs to completion (or until END)
   - Returns the final state as a dict
   - Use when you want the complete result at once

2. graph.astream(initial_state)
   - Runs asynchronously, yields state snapshots after each node
   - You see intermediate results as each node finishes
   - LexAgent uses this: it shows a spinner while each node runs

Example (simplified from lexagent/cli.py):
   async for snapshot in graph.astream(initial_state):
       for node_name, node_state in snapshot.items():
           console.print(f"→ {node_name} complete")

The `snapshot` is a dict like:
   {"intake": {"matter_type": "writ petition", "messages": [...]}}
""")

# ──────────────────────────────────────────────
# THE COMPLETE LEXAGENT GRAPH (textual)
# ──────────────────────────────────────────────

print("""
LEXAGENT GRAPH (from lexagent/graph.py):

  graph.set_entry_point("intake")
  graph.add_conditional_edges("intake", route_after_intake)
  graph.add_conditional_edges("draft", route_after_draft)
  graph.add_conditional_edges("research", route_after_research)
  graph.add_edge("cite", "review")
  graph.add_edge("review", END)
  graph.add_edge("contract_review", END)

  route_after_intake:
    error? → END
    intake_complete and workflow_mode=="contract_review"? → contract_review
    intake_complete and matter_type in ("legal notice", "affidavit", ...)? → draft (skip research)
    intake_complete? → research
    else → END (wait for more lawyer input)

  route_after_research:
    error? → END
    research_only==True? → END (just show findings, no draft)
    else → draft

  route_after_draft:
    error? → END
    auto_verify_citations AND research_findings exist? → cite
    else → review

FLOW FOR A WRIT PETITION:
  intake → [wait for lawyer] → intake → [wait for lawyer] → intake
  → research → draft → cite → review → END
""")

print("\n=== READ COMPLETE — move on to 02_your_first_graph.py ===")
