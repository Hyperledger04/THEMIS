# Phase 10 — V3 Architecture: LexAgent as a Persistent Legal OS

> **This phase is architectural — code sketches that show patterns, not production code.**
> See `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` in the repo root for the full plan.

---

## Where we are

LexAgent is a good teaching graph. It takes a matter brief, asks clarifying questions, researches Indian case law, drafts a court-ready document with verified citations, and saves the matter to memory.

That is a powerful workflow. But it is still a **workflow** — it runs when the lawyer asks, then stops.

## Where V3 goes

**V3 makes LexAgent a persistent legal OS** — a system that lives alongside the firm, works while the lawyer sleeps, and grows smarter with every matter it handles.

The shift is not about adding features. It is about a different architectural posture:

| LexAgent Today | LexAgent V3 |
|---|---|
| Stateless graph invocations | Persistent matter workspace (Postgres) |
| Runs when you ask | 24/7 background worker |
| One graph does everything | 10 specialist counsel subagents |
| Fixed graph topology | Planner generates per-matter DAGs |
| No cross-run learning | Learning loop updates skills and SOUL.md |

---

## The Five Pillars

### 1. Living Matter Workspace
Every matter has a canonical, Postgres-backed record: structured Facts with provenance, Authorities with treatment history, versioned Drafts. No more state scattered across LexState fields, markdown files, SQLite, and LangGraph checkpoints.

### 2. 24/7 Agent Worker
`lex worker` runs a background job loop. When a document is uploaded overnight, the agent extracts facts, builds a chronology, flags limitation risks, and prepares a morning brief — all before the lawyer arrives. **The agent may draft; it may not file.**

### 3. Bulk Document Intelligence
Upload 200 pages of records. The agent parses, chunks, classifies, extracts facts and dates, maps exhibits, and flags contradictions — automatically. Today you process one document per graph run.

### 4. Dynamic Planner
Today every matter goes through the same hardcoded graph nodes. V3's Planner Counsel generates a DAG of tasks per matter type: a Legal Notice needs different steps than a Writ Petition or an NI Act 138 complaint. Adding a new matter type means adding a template, not editing `graph.py`.

### 5. Learning Loop
After each matter, the agent reflects: which research strategies worked? What risk flags were raised? Insights update `SOUL.md` and the skills library. The system gets better at your practice area over time.

---

## What you will learn in each lesson

### `01_matter_workspace.py` — The Canonical Matter Model
- Why scattered state is dangerous for legal work
- Pydantic V2 models: `Fact`, `Authority`, `Draft`, `Provenance`
- Why every agent-generated fact defaults to `alleged`
- Why `verified=False` on Authority prevents hallucinations from being trusted
- **Contrast:** `lexagent/state.py` (today) vs. a Postgres-backed workspace (V3)

### `02_event_driven_runtime.py` — Events and the Event Bus
- Why isolated graph runs cannot react to each other
- Domain events: `NEW_DOCUMENT`, `LIMITATION_WARNING`, `MORNING_BRIEF_READY`
- Simple in-memory event bus (MVP before Redis/Kafka)
- `causation_id`: tracing event chains for audit logs
- **Contrast:** push-only Telegram messages (today) vs. reactive event subscribers (V3)

### `03_living_agent.py` — The 24/7 Background Worker
- Why LexAgent only works when the lawyer sends a message (today)
- Job model: `process_uploaded_documents`, `deadline_scan`, `morning_brief`, `draft_next_document`
- Async worker loop: Postgres jobs table → pending → running → completed/failed
- **THE APPROVAL RULE:** the agent may read, summarise, extract, draft, analyse, recommend — it must NOT file, send emails, or mutate external systems without explicit lawyer approval
- Morning brief: what happened overnight, deadline alerts, draft candidates

### `04_legal_chamber.py` — Specialist Subagents
- Why one graph doing everything limits quality (today)
- The 10 specialist counsel: Senior, Planner, Research, Statutory, Procedure, Evidence, Drafting, Citation, Risk, Client
- Why division of labour matters: Citation Counsel needs strict verification tools, Risk Counsel needs adversarial prompts — you would not give all tools to one agent
- Senior Counsel coordination: delegate → collect → resolve conflicts → approve
- **Contrast:** single `draft` node (today) vs. Drafting Counsel + Citation Counsel + Risk Counsel (V3)

### `05_dynamic_planner.py` — Planner-Generated Execution DAGs
- Why hardcoded graph topology in `graph.py` does not scale (today)
- `ExecutionDAG` model: nodes, dependencies, approval gates, required tools
- Template DAGs for 3 matter types: Legal Notice, Writ Petition, NI Act 138
- Topological sort: safe execution order from a dependency graph
- MVP → LLM-generated path: templates first, then Planner Counsel generates DAG JSON
- **Contrast:** `build_graph()` in `lexagent/graph.py` (static) vs. `select_template()` (dynamic)

---

## How to run

```bash
pip install pydantic
python 01_matter_workspace.py
python 02_event_driven_runtime.py
python 03_living_agent.py
python 04_legal_chamber.py
python 05_dynamic_planner.py
```

No LangGraph, no LangChain, no external services. Only `pydantic`, `asyncio`, and `datetime`.

---

## Reference

- Full V3 plan: `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` (repo root)
- Current graph: `lexagent/graph.py`
- Current state: `lexagent/state.py`
- Current config: `lexagent/config.py`
- Runtime stubs: `lexagent/runtime/`
