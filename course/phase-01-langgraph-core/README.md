# Phase 1 — LangGraph Core

This is the heart of LexAgent. Everything you learn here maps directly to `lexagent/graph.py` and `lexagent/nodes/`.

---

## The central idea

An AI agent is a loop:
1. Receive some input
2. Decide what to do
3. Do it (call a tool, call an LLM, read memory)
4. Observe the result
5. Decide what to do next
6. Repeat until done

LangGraph formalizes this loop as a **directed graph**:
- **Nodes** = steps (each one is an async Python function)
- **Edges** = connections between steps (always go here next)
- **Conditional edges** = routing decisions (which node to go to based on state)
- **State** = the "file on the table" that every node reads and writes

The graph is compiled once, then invoked repeatedly — once per lawyer request.

---

## How LexAgent's graph works

```
START
  │
  ▼
intake  ──── not done? ──── END  (CLI shows question, waits for lawyer)
  │
  │ done? ──── contract_review mode? ──── contract_review ──── END
  │
  │ matter type is notice/affidavit?
  │ ──── skip research ────┐
  │                        │
  ▼                        │
research                   │
  │ research_only=True ──── END
  │                        │
  ▼   ◄────────────────────┘
draft
  │ no findings? ──── review ──── END
  │
  ▼
cite
  │
  ▼
review ──── END
```

This entire flow is defined in about 60 lines of `lexagent/graph.py`.

---

## Files in this phase

| File | Teaches |
|------|---------|
| `01_what_is_a_graph.py` | StateGraph concept — nodes, edges, state, the mental model |
| `02_your_first_graph.py` | Build and run a minimal 2-node graph from scratch |
| `03_nodes_contract.py` | The exact pattern every LexAgent node follows |
| `04_conditional_routing.py` | add_conditional_edges — the intake loop and branching |
| `05_human_in_the_loop.py` | How LexAgent's intake loop works with the CLI |
| `06_checkpointers.py` | MemorySaver vs Postgres — why state persistence matters |
| `exercises/ex01_build_intake_draft.py` | Build a 2-node agent: intake → draft |
| `exercises/ex02_add_conditional_edge.py` | Add a research node with conditional routing |

---

## Connection to LexAgent code

After this phase, open these files and you will understand every line:
- `lexagent/graph.py` — the graph definition and routing functions
- `lexagent/nodes/intake.py` — the intake node
- `lexagent/nodes/draft.py` — the draft node
- `lexagent/nodes/research.py` — the research node

---

## Install

```bash
pip install langgraph langchain-core
```
