# LexAgent Graph Expansion — Phase 6 Through Phase 10

All diagrams are plain-text ASCII. No mermaid.

---

## Current Phase 6 Graph (Baseline)

Source: `lexagent/graph.py:build_graph()`

```
         START
           |
           v
      +---------+
      |  intake  | <---------+
      |  node    |           |
      +---------+            |
           |                 |
    [route_after_intake]     |
           |                 |
     error |  complete=False-+
       v   |
      END  | complete=True
           v
      +----------+
      | research |
      |   node   |
      +----------+
           |
           | (fixed edge)
           v
      +-------+
      | draft |
      | node  |
      +-------+
           |
    [route_after_draft]
           |
     error |  auto_verify AND findings
       v   |  +-------------------------+
      END  |  |                         |
           |  v                         |
           |  +------+   no verify      |
           |  | cite |   or no findings |
           |  | node |                  |
           |  +------+                  |
           |     |                      |
           |     v                      v
           +---> +--------+
                 | review |
                 |  node  |
                 +--------+
                      |
                      | (fixed edge)
                      v
                    END
```

**Registered nodes:** intake, research, draft, cite, review

**Conditional edges:**
- `intake` → `route_after_intake` → { intake (loop), research, END }
- `draft` → `route_after_draft` → { cite, review, END }

**Fixed edges:** research→draft, cite→review, review→END

**Graph limitations at Phase 6:**
1. Single linear flow — no parallelism
2. No `workflow_mode` support — all inputs go through the same path
3. Contract review not implemented despite being in the brief
4. No human-in-the-loop interrupt points
5. No persistent checkpointer — graph state is not saved between invocations
6. `build_graph()` is called inside `_run_draft()` per CLI invocation — wasteful for concurrent use

---

## Phase 7 Graph Expansion

**New elements:**
- `workflow_mode` routing: draft vs contract_review
- `pii_redact` node before draft (optional, flag-gated)
- `contract_review` node as alternate terminal branch
- Graph compiled ONCE at startup (singleton pattern in `gateway/telegram.py`)

```
         START
           |
           v
      +---------+
      |  intake  | <---------+
      |  node    |           |
      +---------+            |
           |                 |
    [route_after_intake]     |
           |                 |
     error |  complete=False-+
       v   |
      END  | complete=True
           |
           +---> workflow_mode="contract_review"
           |          |
           |          v
           |    +-----------------+
           |    | contract_review |----> END
           |    |      node       |
           |    +-----------------+
           |
           | workflow_mode="draft" (default)
           v
      +----------+
      | research |
      |   node   |
      +----------+
           |
           v
      +------------+
      | pii_redact |  <-- new in Phase 7, flag-gated
      |    node    |      LEX_PII_REDACT=false skips
      +------------+      via conditional edge
           |
           v
      +-------+
      | draft |
      | node  |
      +-------+
           |
    [route_after_draft]
           |
     error | auto_verify AND findings
       v   +---------------------+
      END                        |
                                 v
                            +------+
                            | cite |
                            | node |
                            +------+
                                 |
                                 v
                            +--------+
                            | review |
                            |  node  |
                            +--------+
                                 |
                                 v
                               END
```

**New routing function:**
```python
def route_after_intake(state: LexState) -> str:
    if state.get("error"):
        return END
    if not state.get("intake_complete"):
        return "intake"
    mode = state.get("workflow_mode", "draft")
    if mode == "contract_review":
        return "contract_review"
    return "research"
```

**New routing function for PII:**
```python
def route_after_research(state: LexState) -> str:
    config = LexConfig()  # WHY: must check pii flag
    if state.get("error"):
        return END
    if config.pii_redact:
        return "pii_redact"
    return "draft"
```

**Key Phase 7 graph changes:**
- `research` gets a conditional edge (was a fixed edge) — adds PII routing
- `intake` conditional edge adds `contract_review` branch
- New nodes: `contract_review`, `pii_redact`

**Phase 7 graph DOES NOT change:** cite→review→END chain (stable since Phase 5)

---

## Phase 8 Graph Expansion

**New elements:**
- `procedure_check` node (inline in research or standalone) — procedural next-steps
- `limitation_alert` check in review node (not a new node, extension of review)
- Hearing reminder jobs registered from review node post-graph
- `document_classify` step added to intake (classifies WP/CS/CRL/IA)

```
         START
           |
           v
      +---------+
      |  intake  | <-----------+
      | (+ classify) |         |
      +---------+              |
           |                   |
    [route_after_intake]       |
           |        complete=False
     error |  contract_review  |
       v   |        |          +------+
      END  |        v
           |  +-----------------+
           |  | contract_review |----> END
           |  +-----------------+
           |
           | draft (default)
           v
      +----------+
      | research |
      |   node   |
      | (+proc   |
      |  check)  |
      +----------+
           |
           v
      +------------+
      | pii_redact |
      +------------+
           |
           v
      +-------+
      | draft |
      | node  |
      +-------+
           |
    [route_after_draft]
           |
           +--------------------+
           |                    |
           v                    v
        +------+           +--------+
        | cite |           | review |
        | node |     +---> |  node  |
        +------+     |     | (+lim  |
           |         |     |  alert)|
           +---------+     +--------+
                               |
                               v
                             END
           (post-graph: reminder jobs registered from CLI)
```

**Phase 8 does NOT add new graph nodes for reminders.** APScheduler jobs are registered by `cli.py` AFTER the graph stream completes, not inside the graph. This is intentional — the graph should be pure computation; side effects (job scheduling) happen after.

**Phase 8 does add** `procedure_check` logic inside the research node (not as a separate node) to avoid graph topology changes for a minor feature.

---

## Phase 9 Graph Expansion

**New elements:**
- `citation_chain` node in parallel with review (LangGraph `Send` API)
- `contradiction_check` node between cite and review
- Hearing prep sub-graph (separate compiled graph, invoked from CLI)
- `hearing_intake`, `hearing_draft` nodes in the hearing prep sub-graph
- `ratio_extractor` step inside research node (LLM pass, flag-gated)

### Main Graph with Parallel Citation Chain

```
         START
           |
           v
      +-------+
      | intake |<---+
      +-------+     |
           |        |
    [route_after_intake]
           |
    +------+------+
    |             |
    v             v
 contract       draft
 _review        path
   |              |
  END          research
                  |
              pii_redact
                  |
               draft
                  |
    [route_after_draft]
                  |
             +----+----+
             |         |
             v         v
           cite      review (no-verify path)
             |
      +------+------+
      |              |
      v              v  <-- PARALLEL (LangGraph Send API)
contradiction   citation
  _check           _chain
      |              |
      v              v
      +------+-------+
             |
             v
           review
             |
             v
            END
```

**LangGraph Send API pattern for parallel citation_chain:**

```python
# WHY: LangGraph's Send API allows fan-out from a single node to multiple
# nodes that run in parallel, then fan back in. This is the correct pattern
# for running citation_chain and contradiction_check concurrently.
#
# LANGGRAPH: Send() creates a message to a specific node with specific state.
# When multiple Send()s are returned from a conditional edge, they run in parallel.

from langgraph.types import Send

def route_after_cite(state: LexState) -> list[Send]:
    sends = [Send("contradiction_check", state)]
    config = LexConfig()
    if config.citation_chain_enabled and state.get("grounded_citations"):
        sends.append(Send("citation_chain", state))
    return sends
```

**Key Phase 9 graph changes:**
- `cite` conditional edge uses `Send` API for parallel fan-out
- New nodes: `contradiction_check`, `citation_chain`
- These must both complete before `review` runs → add a join node or use LangGraph's built-in join

### Hearing Prep Sub-Graph (Separate Compiled Graph)

```
        START
          |
          v
  +--------------+
  | hearing_     |
  | intake       |
  | (reads       |
  |  MEMORY.md)  |
  +--------------+
          |
          v
  +--------------+
  | research     |  <-- reuses main research node
  | (hearing     |      with hearing_issues query
  |  focused)    |
  +--------------+
          |
          v
  +--------------+
  | hearing_     |
  | draft        |
  | (+opposing   |
  |  args)       |
  +--------------+
          |
          v
  +--------------+
  | review       |  <-- reuses main review node
  +--------------+
          |
          v
         END
```

**Why a separate sub-graph:** The hearing prep flow has different intake requirements (hearing date, last hearing summary), different draft structure (issues list format), and different review criteria (no citation verification needed for argument skeleton). Reusing the main graph with a flag would create too many conditional branches.

**CLI invocation:**
```python
# lexagent/cli.py
@app.command()
def hearing_prep(matter_id: str, hearing_date: str):
    graph = build_hearing_prep_graph()   # separate build function
    asyncio.run(graph.astream(initial_state))
```

---

## Phase 9–10 Full Graph (Combined)

```
START
  |
  v
+--------+
| intake |<---+
| +classify   |
+--------+    |
  |           |
[route_after_intake]
  |
  +--------> contract_review --> END
  |
  v (draft path)
+----------+
| research  |
| +ratio    |
| +proc_chk |
+----------+
  |
  v
+-----------+
| pii_redact|
+-----------+
  |
  v
+-------+
| draft |
+-------+
  |
[route_after_draft]
  |
  +--------> review --> END (no-verify path)
  |
  v
+------+
| cite |
+------+
  |
[Send API fan-out]
  |
  +--------> contradiction_check
  |                  |
  +--------> citation_chain ----+
                                |
                    +-----------v---------+
                    |   (join: both done) |
                    +----------+----------+
                               |
                               v
                          +--------+
                          | review |
                          | +cost  |
                          | +vers  |
                          | +lim   |
                          +--------+
                               |
                               v
                             END
```

---

## Human-in-the-Loop Interrupt Points

LangGraph's `interrupt()` function pauses graph execution and returns control to the caller. The caller can inject new state and resume. This is the correct pattern for lawyer approval gates.

**Where to insert interrupt points:**

| Point | Node | Trigger | What lawyer sees |
|-------|------|---------|-----------------|
| Before filing dispatch | `review` | `--confirm-before-file` flag | Full draft text; confirm/edit/reject |
| Before sending via Telegram | `review` | `LEX_TELEGRAM_CONFIRM=true` | Draft summary; confirm/reject |
| After contradiction detected | `contradiction_check` | any contradiction found | Contradiction details; override/fix |
| After PII detection | `pii_redact` | `LEX_PII_CONFIRM=true` | Redaction log; accept/restore |

**LangGraph interrupt pattern:**
```python
# WHY: interrupt() is LangGraph's built-in mechanism for human-in-the-loop.
# It pauses the graph at the current node and returns the current state to the caller.
# The caller (CLI or Telegram handler) displays state to the human and waits for input.
# When input arrives, the graph is resumed with the updated state.
#
# LANGGRAPH: interrupt() requires a checkpointer to be set in compile().
# Without a checkpointer, the graph cannot save its state across the pause.

from langgraph.types import interrupt

async def run(state: LexState) -> dict:
    if should_confirm(state):
        human_input = interrupt({"draft_output": state["draft_output"]})
        if human_input.get("action") == "reject":
            return {"error": "Draft rejected by lawyer"}
    ...
```

**Checkpointer requirement for interrupt:**
```python
# LANGGRAPH: compile(checkpointer=...) enables persistent state across pauses.
# SqliteSaver is the simplest option — stores state in sessions.db.
# This is also what enables `lex draft --matter-id M001` to resume mid-graph.

from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

conn = sqlite3.connect(str(sessions_db_path))
checkpointer = SqliteSaver(conn)
graph = build_graph().compile(checkpointer=checkpointer)
```

---

## Multi-Agent Supervisor Pattern (Phase 10)

When research involves multiple statutes from different domains (e.g., IPC + RERA + CPC in a real estate criminal fraud case), a supervisor-worker pattern can parallelize statute-specific research.

```
[research node detects multi-domain matter]
         |
         v
  +-----------+
  | research  |
  | supervisor|
  +-----------+
       |
  [Send API fan-out to specialized workers]
       |
  +----+----+----+
  |         |    |
  v         v    v
IPC_     RERA_  CPC_
worker   worker worker
  |         |    |
  +----+----+----+
       |
  [join: all workers done]
       |
       v
  [merged research_findings in state]
       |
       v
    draft node
```

**Implementation approach:**
- Supervisor is the existing `research.py` node
- Workers are sub-graph invocations using `Send` API
- Each worker writes to a `partial_findings` key; supervisor merges them
- This requires LangGraph `Send` API (Phase 9+ pattern)

**When to add this:** Only if a single-threaded research node becomes a measurable bottleneck (> 30 seconds for multi-domain matters). Do not premature-optimize.

---

## Persistent Checkpointing Design

**Which phases need full state snapshots:**

| Phase | Checkpointing need | Mechanism |
|-------|-------------------|----------|
| Phase 7+ | Resume Telegram sessions across bot restarts | `SqliteSaver` in `sessions.db` |
| Phase 8+ | Resume long-running matters across CLI sessions | `SqliteSaver` with `thread_id=matter_id` |
| Phase 9+ | Resume interrupted hearing prep | `SqliteSaver` with `thread_id=matter_id:hearing_date` |
| Phase 10+ | Multi-lawyer shared matter checkpoints | `AsyncSqliteSaver` with workspace-scoped thread IDs |

**Thread ID design:**
```python
# WHY: LangGraph checkpointer uses thread_id to namespace state.
# Using matter_id as thread_id means every matter has its own checkpoint sequence.
# This enables `lex draft --matter-id M001` to resume exactly where it left off,
# even if the graph was interrupted mid-node.

config = {"configurable": {"thread_id": state["matter_id"]}}
graph.astream(initial_state, config=config)
```

**Key constraint:** `SqliteSaver` uses `sqlite3` which is not async-safe under concurrent writes.
For Phase 7 (concurrent Telegram users), use `AsyncSqliteSaver` (LangGraph 0.2+) with WAL mode:
```python
conn = await aiosqlite.connect(str(sessions_db_path))
await conn.execute("PRAGMA journal_mode=WAL")
checkpointer = AsyncSqliteSaver(conn)
```
