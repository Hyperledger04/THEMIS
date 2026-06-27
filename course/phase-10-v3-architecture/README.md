# Phase 10 — V3 Architecture: LexAgent (Themis) as a Persistent Legal OS

> **This phase combines architectural code sketches with three features already shipped to the codebase.**
> Full V3 plan: `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` in the repo root.
> Package rename note: all source is now `themis/` (CLI is still `lex`, data dir is `~/.themis/`).

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

---

## Part 2 — doc-haus Bridge Features (already shipped)

Three patterns from the open-source [doc-haus](https://github.com/sure-scale/doc-haus) TypeScript legal AI were ported to this Python stack. They ship **before** the full V3 planner and subagent contracts because they are independent of that infrastructure.

> These are not sketches. The code is live in `themis/`.

### `06_redline_docx.py` — OOXML Tracked-Changes Redlining

**The gap:** `docx_writer.py` only writes clean files. There is no way to show what changed between contract versions.

**The fix:** `themis/tools/redline.py` diffs original `.docx` paragraphs against revised text using `difflib`, then injects `<w:del>` / `<w:ins>` OOXML elements directly via `lxml`. Word opens the file showing tracked changes natively — no external redline service needed.

**CLI:** `lex draft "revise NDA" --redline /tmp/original.docx --output /tmp/revised.docx`

**Why now:** The V3 roadmap initially deferred this "until draft versioning is stable." doc-haus shows the implementation is independent of versioning. OOXML injection is purely a tool concern.

### `07_adversarial_chamber.py` — Adversarial Multi-Agent Review

**The gap:** `themis/nodes/review.py` is a single-pass LLM call. One model checking its own output does not catch subtle legal errors.

**The fix:** `themis/nodes/chamber.py` runs three sequential LLM calls:
1. **Reviewer** — finds numbered issues in the draft
2. **Challenger** — marks each issue VALID / OVERSTATED / WRONG
3. **Summarizer** — synthesises both into ACTION ITEMs + RISK LEVEL

**CLI:** `lex draft "review vendor agreement" --chamber`

**Why sequential, not parallel:** the Challenger must see the Reviewer's output; the Summarizer must see both. This is the same topological constraint as any DAG dependency — lesson 5 (`05_dynamic_planner.py`) makes this precise.

**V3 future:** Phase 11 replaces this single node with ten isolated specialist subagents (Senior, Research, Statutory, Procedure, Evidence, Drafting, Citation, Risk, Client, Planner Counsel). The interface (`chamber_review` in state) stays the same.

### `08_grid_analysis.py` — Cross-Document Grid Analysis

**The gap:** `document_qa` can answer one question about one document. Due diligence on 50 contracts requires the same question answered across every document simultaneously.

**The fix:** `themis/nodes/grid.py` runs `asyncio.gather` over every `(question, doc)` pair in the matter, producing a `{question: {doc_name: answer}}` matrix rendered as a Rich table.

**CLI:** `lex grid my-matter -q "What is the notice period?" -q "Who bears indemnity?" --csv output.csv`

**Why `asyncio.gather` here:** each LLM call is independent (no shared mutable state). Parallel is O(max single call) instead of O(questions × docs). This is the key insight from Phase 0 async/await — concurrency without threading.

**V3 future:** Phase 4 (Bulk Document Intelligence) replaces `_list_matter_docs()` with a `workspace.repository.list_documents(matter_id)` call. The node interface is unchanged.

---

## Lessons in this phase

| File | Topic | Status |
|------|-------|--------|
| `01_matter_workspace.py` | Canonical matter model (Pydantic) | Sketch |
| `02_event_driven_runtime.py` | Event bus + domain events | Sketch |
| `03_living_agent.py` | 24/7 background worker | Sketch |
| `04_legal_chamber.py` | Specialist subagents | Sketch |
| `05_dynamic_planner.py` | Planner-generated DAGs | Sketch |
| `06_redline_docx.py` | OOXML tracked-changes redlining | **Shipped** (`themis/tools/redline.py`) |
| `07_adversarial_chamber.py` | Adversarial review chamber | **Shipped** (`themis/nodes/chamber.py`) |
| `08_grid_analysis.py` | Cross-document grid analysis | **Shipped** (`themis/nodes/grid.py`) |

---

## How to run

```bash
# Architecture sketches — no external deps
pip install pydantic
python 01_matter_workspace.py
python 02_event_driven_runtime.py
python 03_living_agent.py
python 04_legal_chamber.py
python 05_dynamic_planner.py

# doc-haus bridge features — requires themis installed
cd /Users/anshoosareen/Lexagent && uv sync
python course/phase-10-v3-architecture/06_redline_docx.py
python course/phase-10-v3-architecture/07_adversarial_chamber.py
python course/phase-10-v3-architecture/08_grid_analysis.py
```

---

## Reference

- Full V3 plan: `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` (repo root)
- Current graph: `themis/graph.py`
- Current state: `themis/state.py`
- Current config: `themis/config.py`
- Runtime: `themis/runtime/`
- Redline tool: `themis/tools/redline.py`
- Chamber node: `themis/nodes/chamber.py`
- Grid node: `themis/nodes/grid.py`
