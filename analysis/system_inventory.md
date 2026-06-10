# System Inventory

**Source:** CRG graph analysis + direct file inspection
**Graph:** 237 files · 2,196 nodes · 16,156 edges · 17 communities

---

## Per-Module Inventory

### `lexagent/graph.py`
**Purpose:** Compile and cache the LangGraph StateGraph. Define routing functions.
**Dependencies:** All node modules, LexConfig, LexState, langgraph
**Inputs:** LexConfig (for Postgres URL, routing flags)
**Outputs:** Compiled runnable graph (MemorySaver or AsyncPostgresSaver)
**Technical debt:** Build function instantiates `LexConfig()` inline — config instantiated twice per graph build. `_NO_RESEARCH_TYPES` hardcoded tuple; should be config or skill manifest.
**Importance:** Critical — this is the execution spine.

---

### `lexagent/state.py`
**Purpose:** Define `LexState` TypedDict — the shared state bag flowing through every graph node.
**Dependencies:** None (pure typing)
**Inputs:** N/A (schema definition)
**Outputs:** N/A (schema definition)
**Technical debt:** 57+ fields mixing: ephemeral run flags (`intake_complete`, `citations_verified`), durable matter facts (`parties`, `jurisdiction`), gateway identity (`telegram_user_id`, `voice_session_id`, `firm_id`), output artifacts (`draft_output`, `docx_path`), and RAG intermediates (`retrieval_chunks`, `raptor_tree`). This TypedDict is doing the work that the workspace repository is supposed to own. V3 requires that nodes read/write workspace objects; `LexState` should carry only IDs into the workspace.
**Importance:** Critical — every node touches this. Every bug starts here or ends here.

---

### `lexagent/config.py` — `LexConfig`
**Purpose:** Centralized Pydantic settings for every configurable value.
**Dependencies:** pydantic-settings
**Inputs:** `.env`, `~/.lexagent/.env`
**Outputs:** `LexConfig` instance consumed by all modules
**Technical debt:** ~80 fields. Some tool flags appear redundant (e.g., `enable_kanoon` AND `kanoon_backend`). Two env files loaded in reverse-priority order — documented but unusual.
**Importance:** Very high — CRG shows 75 in-degree edges into `LexConfig`. Every module depends on it. It is the single source of behavioral truth.

---

### `lexagent/nodes/`
**Purpose:** Individual graph execution steps. Each file exports a `run(state) → dict` async function.

| Node | LOC | Function | Status |
|------|-----|----------|--------|
| intake.py | ~300 | Structured intake, clarifying questions, skill selection | Working |
| draft.py | 414 | Document drafting via LLM with soul/skill injection | Working |
| research.py | 419 | Legacy research (Kanoon stub + tools) | Working (legacy path) |
| react_research.py | 344 | ReAct loop with tool selection | Partial — ReAct structure exists, no hypothesis loop |
| retrieve.py | ~200 | BM25 + TF-IDF hybrid retrieval | Working |
| cite.py | ~235 | Citation extraction and verification | Working |
| review.py | 100 | Length check, jurisdiction check, .docx write | Thin |
| contract_review.py | ~300 | PDF ingestion + clause risk analysis | Working |
| document_qa.py | ~200 | Q&A over uploaded documents | Working |

**Technical debt:** `research.py::run` has 105 out-degree (CRG hub). `react_research.py::run` has 50 out-degree. Both are monolithic. `review.py` is only 100 lines for a node named "review" — it does structural validation, not legal quality review.
**Importance:** Highest — these produce the user-visible output.

---

### `lexagent/tools/`
**Purpose:** Self-registering tool implementations called by nodes via `ToolRegistry`.

| Tool | Purpose |
|------|---------|
| registry.py | Decorator-based registration, `get_langchain_tools()` |
| kanoon.py / kanoon_api.py / kanoon_fallback.py | Indian Kanoon scraper/API/Playwright |
| kanoon_utils.py | Shared utilities |
| retriever.py | BM25 + TF-IDF hybrid retriever |
| reranker.py | Cross-encoder re-ranker |
| chunker.py | Parent-child chunking |
| query_expander.py | Indian legal synonym expansion |
| raptor_summarizer.py | Hierarchical RAPTOR clusters |
| legal_kg.py | Entity extraction (113 out-degree in `extract_entities`) |
| limitation.py | Limitation period calculator |
| docx_writer.py | .docx generation (44 out-degree in `write_docx`) |
| court_fees.py | Court fee calculator |
| courtlistener.py | CourtListener US API (stub-mode default) |
| duckduckgo_search.py / tavily_search.py / serpapi_search.py / perplexity_search.py | Web search backends |
| firecrawl_fetch.py / jina_reader.py | Web fetch/read |

**Technical debt:** Too many search backends (5 web search tools). Registry has no capability metadata — callers cannot ask "which tools support citation verification?" No per-firm tool enablement model.
**Importance:** High — tools are how research quality is actually determined.

---

### `lexagent/workspace/`
**Purpose:** Typed matter workspace — Pydantic models and Postgres CRUD.

| File | Purpose |
|------|---------|
| models.py | 17 Pydantic models: Matter, Document, Fact, Chronology, Evidence, Party, Issue, Authority, Draft, FeedbackItem, Deadline, Task, ResearchMemo, RiskAnalysis, StylePreference, PlaybookNote, SourceAnchor |
| repository.py | 1,085-line `PostgresWorkspaceRepository` with firm_id+matter_id isolation on every query |
| migrations/ | SQL migration files |

**Technical debt:** Workspace is designed correctly but **not yet wired into the graph**. Nodes write to `LexState` dict fields, not to workspace objects. The `Authority` model in workspace has `court_tier`, `corpus_namespace`, `verified_excerpt` — the graph's `cite.py` does not populate these fields.
**Importance:** Very high — this is the V3 product core. Its quality is excellent; its adoption by nodes is zero.

---

### `lexagent/runtime/`
**Purpose:** Job scheduling, execution, and lifecycle for 24/7 living agent.

| File | Purpose |
|------|---------|
| models.py | AgentRun, AgentJob, AgentStep, AgentToolCall, AgentArtifact, AgentApproval, AgentNotification, RuntimeEvent |
| worker.py | `RuntimeWorker` — asyncio poll loop, handler registry, cost brakes, approval enforcement |
| jobs.py | Job handlers — only `handle_process_uploaded_documents` implemented (~500 lines) |
| brakes.py | `CostLedger`, `HaltFlag` — session/job cost caps and idle timeouts |
| postgres.py | Postgres persistence for runtime objects |
| migrations/ | SQL migration files |

**Technical debt:** `AgentKind` enum declares 10 agent types (document_processing, chronology, evidence, ni_act_compliance, research, risk, drafting, verification, notification, learning). Only one handler exists (`process_uploaded_documents`). Nine job types are named but unimplemented.
**Importance:** Very high — V3's living agent runs on this. The skeleton is sound; it needs nine more handlers.

---

### `lexagent/ingestion/`
**Purpose:** Document intake pipeline — text extraction, chunking, fact/date extraction, chronology building.

| File | Purpose |
|------|---------|
| documents.py | `ingest_file()` — PDF/DOCX/text → `IngestedDocument` with pages |
| extractors.py | `extract_from_pages()` — LLM-based fact/party/issue/date/evidence extraction |
| chronology.py | Chronology item extraction and sorting |
| anchors.py | `SourceAnchor` creation for extracted items |

**Dependencies:** workspace/models.py, workspace/repository.py, LLM
**Technical debt:** OCR fallback disabled by default (`pdf_ocr_fallback=False`). File storage is local filesystem — no object store integration yet.
**Importance:** High — this is how bulk document intelligence enters the system.

---

### `lexagent/gateway/`
**Purpose:** Thin adapters for each interface channel.

| File | Purpose |
|------|---------|
| control_plane.py | FastAPI app with `/run`, `/status`, `/chat` endpoints |
| telegram.py | Telegram Bot API, inline buttons, session management |
| voice.py | Twilio + WebSocket voice gateway, STT/TTS pipeline |
| inference.py | Voice inference (model call abstraction for voice) |
| setup_wizard.py | `lex setup` interactive first-run wizard |
| anonymizer.py | PII anonymization middleware |
| tier_middleware.py | Inference tier enforcement |
| integrations.py | External service integrations |

**Technical debt:** Control plane still uses a token verification path that does not consistently enforce the security package (`SecurityContext`). CORS wildcard not enforced off in enterprise mode. Voice gateway is the highest-criticality flow (CRG: 0.728) despite being a tertiary channel for legal work.
**Importance:** Medium — gateways are necessary but should be thin. Over-investment risk here.

---

### `lexagent/memory/`
**Purpose:** Lawyer identity (SOUL.md), matter memory (MEMORY.md + state.json), SQLite sessions.

**Technical debt:** File-based memory is not authoritative legal state. Matter memory is append-only markdown — not queryable, not typed. Session isolation in SQLite is not enforced by `firm_id` (only by `user_id`). The V3 Memory OS (7 layers) is not started.
**Importance:** Medium — functional for personal mode; must be replaced before multi-tenant.

---

### `lexagent/security/`
**Purpose:** Enterprise-grade security primitives.

| File | Purpose |
|------|---------|
| crypto.py | AES-256-GCM + HKDF encryption |
| tokens.py | JWT access/refresh token generation and verification |
| permissions.py | RBAC `_has_permission()` — 33 in + 33 out degree (CRG bridge) |
| audit.py | Audit log with 7-year retention support |
| context.py | `SecurityContext` request context |
| tiers.py | Inference tier floor enforcement |

**Technical debt:** Security package is complete but **not consistently wired into gateways**. `_has_permission` is a bridge node (high betweenness centrality) — a change here ripples everywhere. Control plane does not always enforce `SecurityContext` for every route.
**Importance:** Very high — legal data. One gap = professional liability.

---

### `lexagent/agents/`
**Purpose:** Agent persona system (not specialist counsel agents).
- `faces.py` — Persona definitions (name, tone, style, description)
- `registry.py` — `AgentRegistry` for persona lookup

**Technical debt:** These are *character skins* for the LLM, not functional subagents with isolated state or specialist knowledge. The V3 "Chamber" architecture (Senior Counsel, Research Counsel, etc.) is not started.
**Importance:** Low currently. Will become critical when chamber agents are built.

---

### `lexagent/learning/`
**Purpose:** Capture and apply feedback to improve future outputs.
- `feedback.py` — `FeedbackService` (~102 lines)
- `preferences.py` — `StylePreferenceService` (~175 lines)
- `playbooks.py` — `PlaybookNoteService` (~157 lines)

**Technical debt:** Services exist but are **not called by any node during draft/research execution**. Preferences are not injected into prompts. Feedback is stored but not retrieved. The learning loop is write-only; read side is missing.
**Importance:** High strategically — this is the compounding moat. Currently zero leverage.

---

### `lexagent/kb/`
**Purpose:** Qdrant knowledge base collections.
- `collections.py` — Collection management, vector upsert/query

**Technical debt:** All-MiniLM-L6-v2 embeddings (384d). Single collection model — no corpus namespace partitioning (§9 of roadmap). Jurisdictional conflation (§11A Failure Mode 2) is possible until collections are namespaced.
**Importance:** Medium — powers retrieval quality.

---

### `lexagent/skills/`
**Purpose:** Markdown skill files loaded based on matter type triggers.
- `loader.py` — Scan dir, match by trigger keywords, inject content
- Skill `.md` files with YAML frontmatter

**Technical debt:** Skill manifests lack `workflow_dag`, `tools_allowed`, `approval_gates`, `tests`, and `versioning` fields. Skills are static text injection — no skill-specific tool selection or routing.
**Importance:** Medium — elegant mechanism; needs V3 upgrade to manifests.

---

### `lexagent/ui/`
**Purpose:** CLI rendering (Rich spinners, progress bars, live output).
- `live.py` — Rich live display
- `spinner.py` — Contextual legal loading messages

**Technical debt:** No `terminal/` subdirectory. "Beast Terminal" Legal IDE not begun.
**Importance:** Low for MVP; important for power-user adoption.

---

## Runtime Flow Diagram

```
User
  |
  ├─ CLI (lex draft "...")
  ├─ Telegram (inline buttons)
  ├─ Voice (Twilio / WebSocket)
  └─ Control Plane REST (FastAPI)
          |
          ↓
    [Auth / Tenant / Rate Limit]   ← security/ (partially enforced)
          |
          ↓
    LangGraph StateGraph            ← graph.py
    (intake → research → retrieve → draft → cite → review)
          |
          ├─ Tools (Kanoon, search, retriever, limitation, legal_kg)
          ├─ Skills (markdown injection)
          ├─ SOUL.md (lawyer identity)
          └─ Workspace (reads NONE; writes NONE yet)
          |
          ↓
    Outputs
    ├─ draft_output (text in LexState)
    ├─ .docx file (filesystem)
    ├─ citation_status
    └─ risk_annotations
          |
          ↓
    Persistence
    ├─ LangGraph checkpointer (MemorySaver / Postgres)
    ├─ SQLite sessions.db
    ├─ ~/.lexagent/matters/{id}/MEMORY.md
    └─ Qdrant (optional)

[Separate path — not yet connected to graph]
RuntimeWorker
  ├─ polls Postgres agent_jobs
  ├─ executes handle_process_uploaded_documents
  └─ updates workspace via PostgresWorkspaceRepository
```

**The critical disconnect:** The graph and the runtime worker operate independently. Neither reads from the workspace at runtime. The workspace repository exists and is correct; no node calls it.
