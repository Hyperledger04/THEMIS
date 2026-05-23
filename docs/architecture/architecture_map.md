# LexAgent Architecture Map

**Phase:** 6 (Complete) — RAGFlow core features (PDF parsing, query expansion, RAPTOR, GraphRAG, LLM re-ranker)
**Date:** 2026-05-18

---

## High-Level System Diagram

```
                         ┌─────────────────────────────────────────┐
                         │               CLI (cli.py)               │
                         │  `lex draft` / `lex setup` / `lex search`│
                         │  asyncio.run(_run_draft(...))             │
                         └──────────────┬──────────────────────────┘
                                        │ build_graph().astream(state)
                                        ▼
                  ┌────────────────────────────────────────────┐
                  │           LangGraph StateGraph              │
                  │                                            │
                  │  ┌─────────┐     ┌──────────┐             │
                  │  │ intake  │────▶│ research │             │
                  │  │  node   │◀─┐  │   node   │             │
                  │  └─────────┘  │  └────┬─────┘             │
                  │     (loop)    │       │                    │
                  │               │  ┌────▼─────┐             │
                  │               │  │  draft   │             │
                  │               │  │   node   │             │
                  │               │  └────┬─────┘             │
                  │               │       │  (conditional)    │
                  │               │  ┌────▼─────┐             │
                  │               │  │   cite   │             │
                  │               │  │   node   │             │
                  │               │  └────┬─────┘             │
                  │               │       │                    │
                  │               │  ┌────▼─────┐             │
                  │               │  │  review  │────▶ END    │
                  │               │  │   node   │             │
                  │               │  └──────────┘             │
                  └────────────────────────────────────────────┘
                                        │
               ┌────────────────────────┼──────────────────────┐
               ▼                        ▼                       ▼
     ┌──────────────────┐   ┌─────────────────────┐  ┌──────────────────┐
     │   Memory System  │   │   Tools Registry    │  │  Skills System   │
     │                  │   │                     │  │                  │
     │ ~/.lexagent/     │   │ ToolRegistry._tools │  │ lexagent/skills/ │
     │   SOUL.md        │   │  - check_limitation │  │  civil_litigation│
     │   matters/{id}/  │   │                     │  │  legal_notice    │
     │     MEMORY.md    │   │ HybridRetriever      │  │  legal_contract  │
     │     state.json   │   │ LLMReranker          │  │                  │
     │   sessions.db    │   │ RaptorSummarizer     │  │ ~/.lexagent/     │
     │   llm_cache/     │   │ LegalKnowledgeGraph  │  │   skills/        │
     └──────────────────┘   └─────────────────────┘  └──────────────────┘
```

---

## Component Inventory

| Component | File(s) | Purpose |
|-----------|---------|---------|
| LexState | `lexagent/state.py` | Central TypedDict flowing through all nodes |
| Graph | `lexagent/graph.py` | StateGraph assembly; routing functions |
| Config | `lexagent/config.py` | All environment-driven config (LexConfig) |
| CLI | `lexagent/cli.py` | Typer app; interactive intake loop; session persistence |
| Intake Node | `lexagent/nodes/intake.py` | LLM-driven field extraction + clarifying questions |
| Research Node | `lexagent/nodes/research.py` | Kanoon search + limitation check + RAPTOR + GraphRAG |
| Draft Node | `lexagent/nodes/draft.py` | LLM document drafting; dual-layer caching |
| Cite Node | `lexagent/nodes/cite.py` | Citation extraction; chunk-level grounding; fallback corpus check |
| Review Node | `lexagent/nodes/review.py` | Validation gate; word-count check; .docx export trigger |
| LLM Factory | `lexagent/nodes/_llm.py` | get_llm(); setup_litellm_cache() |
| Tool Registry | `lexagent/tools/registry.py` | Self-registration decorator; get_langchain_tools() |
| Kanoon Scraper | `lexagent/tools/kanoon.py` | Playwright browser automation for Indian Kanoon |
| Limitation Tool | `lexagent/tools/limitation.py` | Indian Limitation Act 1963 lookup + deadline calc |
| Hybrid Retriever | `lexagent/tools/retriever.py` | BM25 + TF-IDF cosine; child/parent chunk hierarchy |
| Chunker | `lexagent/tools/chunker.py` | Structure-preserving splitter; PDF/DOCX/TXT extraction |
| Query Expander | `lexagent/tools/query_expander.py` | Indian legal synonym expansion for BM25 |
| RAPTOR Summarizer | `lexagent/tools/raptor_summarizer.py` | Hierarchical cluster summarization via LLM |
| Legal KG | `lexagent/tools/legal_kg.py` | Regex NER + in-memory knowledge graph; SQLite persistence |
| LLM Reranker | `lexagent/tools/reranker.py` | Cross-encoder re-ranking via LLM batch scoring |
| Docx Writer | `lexagent/tools/docx_writer.py` | Court-ready .docx output with citation appendix |
| Skills Loader | `lexagent/skills/loader.py` | YAML frontmatter parser; two-directory merge; keyword match |
| Civil Litigation Skill | `lexagent/skills/civil_litigation.md` | CPC structure templates; mandatory citations |
| Legal Notice Skill | `lexagent/skills/legal_notice.md` | Notice templates; S.80/S.138 risk flags |
| Legal Contract Skill | `lexagent/skills/legal_contract.md` | Contract drafting templates |
| SOUL Memory | `lexagent/memory/soul.py` | ~/.lexagent/SOUL.md read/write/wizard |
| Matter Memory | `lexagent/memory/matter_memory.py` | Per-matter MEMORY.md append-log + state.json snapshot |
| Session Store | `lexagent/memory/session_store.py` | SQLite FTS5 sessions; search_sessions() |
| Base System Prompt | `lexagent/prompts/base_system.md` | Core LLM identity + citation rules + output format |
| Tool Guidance Prompt | `lexagent/prompts/tool_guidance.md` | Tool usage instructions injected for Phase 4+ |

---

## Data Flow Narrative

### 1. Brief → Intake

The lawyer runs `lex draft "I need an injunction for a property dispute in Delhi"`. The CLI creates a `LexState` with `user_input` set and `intake_complete=False`. The graph starts at the `intake` node.

The intake node calls the LLM with `INTAKE_SYSTEM_PROMPT` (inlined in `nodes/intake.py`, not in `prompts/`) and the full message history. The LLM returns a JSON object with extracted fields (`matter_type`, `parties`, `jurisdiction`, `purpose`) and any `clarifying_questions`. The node also loads `SOUL.md` if present and auto-selects a skill by calling `skills/loader.py:load_skill()`.

If any required field is missing, the graph routes back to intake. The CLI prints the questions, collects answers, appends them to `state["messages"]`, and re-runs the graph. This loop repeats up to 5 times (hardcoded in `cli.py:_run_draft`).

When all four required fields (`matter_type`, `parties`, `jurisdiction`, `purpose`) are present, `intake_complete=True` is set and the graph moves to `research`.

### 2. Research

The research node builds a query string from intake fields and queries Indian Kanoon (stub or Playwright). It runs the `check_limitation` tool (via `ToolRegistry.get("check_limitation")`). It extracts statutes from fetched judgment text using `_STATUTE_RE`.

If `config.raptor_enabled=True`, it builds a RAPTOR tree from the findings and appends synthetic summary entries back into `research_findings`. If `config.graphrag_enabled=True`, it runs `LegalKnowledgeGraph.add_text()` over all findings and stores the entity graph in `state["entity_graph"]`.

Research feeds `research_findings`, `statutes_cited`, `limitation_analysis`, and optionally `raptor_tree` and `entity_graph` into state, then always routes to `draft`.

### 3. Draft

The draft node builds a user-turn instruction from all intake fields. If `research_findings` are present, it injects them as "Verified case law to use". If no findings exist, it warns the LLM to flag any citations as `[UNVERIFIED — human review required]`.

For Anthropic providers with caching enabled, it calls `litellm.acompletion()` with `cache_control` blocks (Layer 2). For all other providers, it uses `ChatLiteLLM` with `get_llm()` (Layer 1 disk cache only).

The LLM output is returned as `draft_output`. A regex extraction picks the "Plain English Summary" from the output into `plain_english_summary`.

### 4. Cite (conditional)

The `route_after_draft` function routes to `cite` only if `config.auto_verify_citations=True` AND `research_findings` is non-empty. Otherwise it skips to `review`.

The cite node extracts Indian citation strings from the draft using `_CITATION_RE`. For each citation it queries `HybridRetriever` (built from research_findings) to find a matching chunk. Citations that get a chunk match are marked `verified=True`; others go to `unverified_citations`. The results are stored in `grounded_citations` and `retrieval_chunks`.

The `HybridRetriever` fuses BM25Okapi (via `rank-bm25`) and TF-IDF cosine (via `sklearn`) scores. If `query_expansion=True`, each BM25 query is first expanded with Indian legal synonyms from `tools/query_expander.py`. If `reranker_enabled=True` (not used in cite node directly — only available via `retriever.retrieve_reranked()`), an LLM cross-encoder scores candidates.

### 5. Review

The review node checks: (a) no `unverified_citations`, (b) draft word count within `_WORD_LIMITS` for the matter type, (c) draft is not empty. Issues become `risk_annotations`. If `state["docx_path"]` is set (via `--output` flag), `docx_writer.write_docx()` is called and the absolute path is stored back in `docx_path`.

Review routes unconditionally to END.

### 6. Post-Graph

After the graph stream completes, `cli.py:_save_session_and_memory()` runs:
- `session_store.save_session()` inserts a row into `~/.lexagent/sessions.db` (FTS5 indexed)
- `matter_memory.save_matter_memory()` appends an entry to `~/.lexagent/matters/{matter_id}/MEMORY.md` and writes `state.json`

---

## Memory Subsystem Layout

```
~/.lexagent/
├── SOUL.md                        # Lawyer identity (name, bar, style prefs)
├── sessions.db                    # SQLite FTS5 — all sessions indexed
├── llm_cache/                     # LiteLLM disk cache (Layer 1)
└── matters/
    └── {matter_id}/
        ├── MEMORY.md              # Append-only session log (markdown)
        └── state.json             # Last serialised LexState snapshot
```

**SOUL.md** is loaded by `memory/soul.py:load_soul()`. It is called in the intake node (if not already in state) and injected into every draft system prompt.

**MEMORY.md** is append-only. Each session adds a block with timestamp, matter type, parties, summary, statutes, cases, unverified citations, and errors. There is no RAG retrieval over MEMORY.md yet (noted as a Phase 5 TODO in the code comments).

**state.json** stores all serialisable LexState fields (excluding `messages` which contains non-JSON objects). This is the mechanism for `lex draft --matter-id` continuation.

**sessions.db** has three tables: `sessions` (main), `sessions_fts` (FTS5 virtual), `schema_version`. Triggers keep FTS5 in sync. The `entity_graphs` table is created on demand by `legal_kg.py:save_entity_graph()`.

---

## Tool + Skills Subsystem Layout

### Tool Registry

`ToolRegistry` is a class-level dictionary (`_tools: dict[str, dict]`). Tools self-register via `@ToolRegistry.register(name, description)` decorator at module import time. Currently only one tool is registered:

- `check_limitation` (registered in `tools/limitation.py`, imported by `nodes/research.py`)

`get_langchain_tools()` returns LangChain `StructuredTool` objects for `bind_tools()` — but `bind_tools()` is **not called anywhere in the graph**. The registry's LangChain integration is prepared but unused.

### Skills System

Skills are `.md` files with YAML frontmatter (`name`, `trigger_keywords`, `matter_types`). Two directories are scanned:
1. Bundled: `lexagent/skills/` (3 skills: `civil_litigation`, `legal_notice`, `legal_contract`)
2. User: `~/.lexagent/skills/` (user-editable overrides)

Matching is two-pass: (1) exact `matter_types` match, then (2) `trigger_keywords` substring. User skills with the same `name` override bundled ones.

Skill loading happens in the **intake node** (not draft), so the selected skill content is in `state["active_skill"]` before the draft node runs. The skill content is injected into the system prompt in `draft.py:build_system_prompt_blocks()`.
