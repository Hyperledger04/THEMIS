# LexAgent Impact Radius

This document maps the blast radius of changes to each major module, test coverage, and the critical path for a basic `lex draft` invocation.

---

## Blast Radius Scores

**HIGH** — change breaks multiple nodes or the entire graph
**MEDIUM** — change breaks one node or one subsystem
**LOW** — change breaks a single isolated function or test

---

## Module-by-Module Impact Analysis

### `lexagent/state.py` — LexState

| Attribute | Value |
|-----------|-------|
| Blast radius | HIGH |
| Dependents | Every node (`intake`, `research`, `draft`, `cite`, `review`), `cli.py`, `memory/matter_memory.py`, `memory/session_store.py`, `tools/docx_writer.py` |
| Tests | `tests/test_state.py` (168 lines, comprehensive field checks) |

**What breaks if this module changes:**
- Adding a field: `_blank_state()` in cli.py must be updated; `_minimal_state()` in test_state.py must be updated; `_save_state_snapshot()` in matter_memory.py will handle it automatically (iterates keys)
- Removing a field: Any node reading that field via `state.get()` silently returns `None` — no crash, silent failure
- Renaming a field: All `state.get("old_name")` calls across 5 nodes and 3 memory files must be updated manually; no static enforcement since TypedDict is not runtime-validated by LangGraph

**Specific risk:** `cause_of_action_date` is accessed in `research.py` but is NOT in `LexState`. If the field is added (the correct fix), it must also be added to `_blank_state()`, `_minimal_state()`, intake prompt JSON schema, and intake node extraction logic.

---

### `lexagent/graph.py` — Graph Assembly

| Attribute | Value |
|-----------|-------|
| Blast radius | HIGH |
| Dependents | `cli.py` (calls `build_graph()`); indirectly all nodes |
| Tests | No dedicated test for graph.py; graph is only exercised end-to-end in node tests via direct `run()` calls |

**What breaks if this module changes:**
- Changing `route_after_draft`: directly changes when `cite` runs vs when it's skipped — affects all citation verification behaviour
- Adding a new node: must be wired with `add_node()` AND an edge; forgetting either causes a `langgraph.errors.InvalidUpdateError` at compile time
- Changing entry point from `intake`: breaks the entire interactive loop in cli.py

**Phase 7 risk:** The current graph is compiled once in `_run_draft()` per CLI invocation. For a Telegram gateway, `build_graph()` should be called once at startup and reused.

---

### `lexagent/config.py` — LexConfig

| Attribute | Value |
|-----------|-------|
| Blast radius | HIGH |
| Dependents | Every module that instantiates `LexConfig()` — intake, research, draft, cite, _llm, cli, kanoon, graph (routing fn) |
| Tests | `tests/test_caching.py` (caching config), no dedicated config test |

**What breaks if this module changes:**
- Renaming a field: all `config.field_name` references across 6+ files must be updated
- Changing a default value: affects all tests that don't set the env var explicitly
- Adding a new field for Phase 7 (Telegram): requires adding `telegram_*` fields (already present: `telegram_bot_token`, `telegram_allowed_users`)

**Note:** `kanoon.py` has `config = LexConfig()` at module level (line 21), meaning config is read at import time. Tests that need to override `kanoon_headless` must monkeypatch `lexagent.tools.kanoon.config` specifically, not just set env vars after import.

---

### `lexagent/nodes/intake.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `graph.py` (registered), `cli.py` (drives the loop) |
| Tests | No dedicated `test_intake.py`; intake is tested indirectly through state tests |

**What breaks if this module changes:**
- Changing `REQUIRED_FIELDS`: changes what `intake_complete=True` means; may cause graph to advance with insufficient data
- Changing the JSON schema in `INTAKE_SYSTEM_PROMPT`: may break `_parse_extraction()` if the LLM response format changes
- Changing skill loading call: would break Phase 3 skill injection

**Coverage gap:** The intake node has no dedicated test file. The LLM call is not mocked in any test. This is the only node without test coverage.

---

### `lexagent/nodes/research.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `draft.py` (reads `research_findings`), `cite.py` (builds retriever from findings) |
| Tests | `tests/test_research.py` (stub backend, 107 lines, 8 tests) |

**What breaks if this module changes:**
- Changing the stub result shape: breaks cite node (expects `full_text`, `citation`, `case_name` keys)
- Changing how RAPTOR entries are structured: breaks draft node's citation instruction builder (CRIT-02)
- Removing the `check_limitation` call: removes limitation analysis from all drafts silently

**Phase 7 risk:** Research node has console.print() calls for progress — these would output to server logs in a Telegram gateway. Should be replaced with structured logging.

---

### `lexagent/nodes/draft.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | HIGH |
| Dependents | `cli.py` (reads `draft_output`, `plain_english_summary`), `cite.py` (reads `draft_output`), `review.py` (reads `draft_output`) |
| Tests | No dedicated `test_draft.py` |

**What breaks if this module changes:**
- Changing `_build_draft_instruction()`: affects all LLM output quality; no automated regression test
- Changing the Anthropic vs non-Anthropic branch: different system prompt formats sent
- Removing `_extract_summary()`: `plain_english_summary` always empty; no CLI panel; no session summary in SQLite

**Coverage gap:** Draft node has no test file. This is the most impactful node (produces the final document) and is untested.

---

### `lexagent/nodes/cite.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `review.py` (reads `unverified_citations`, `grounded_citations`), `docx_writer.py` (reads `grounded_citations`) |
| Tests | `tests/test_cite.py` (125 lines) |

**What breaks if this module changes:**
- Changing `_CITATION_RE`: affects which citation strings are extracted and verified; regex patterns are Indian-only
- Changing how `grounded_citations` is structured: breaks `docx_writer.py` which accesses `g["verified"]`, `g["chunk_id"]`, `g["source"]`

---

### `lexagent/nodes/review.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | LOW |
| Dependents | `cli.py` (reads `docx_path`, `risk_annotations`) |
| Tests | `tests/test_review.py` (116 lines, good coverage) |

**What breaks if this module changes:**
- Changing `_WORD_LIMITS`: changes which drafts get flagged as overlong
- Adding a new check: straightforward; adds to `issues` list
- Removing the docx call: `--output` flag silently stops working

---

### `lexagent/tools/retriever.py` — HybridRetriever

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `cite.py` directly; `raptor_summarizer.py` uses `chunker.py` (same dep) |
| Tests | `tests/test_retriever.py` (124 lines) |

**What breaks if this module changes:**
- Changing `RetrievalResult` namedtuple: breaks `cite.py` (accesses `.child`, `.parent`, `.score`, `.bm25_score`, `.vector_score`)
- Changing `from_findings()` signature: breaks the inline construction in `cite.py`
- Removing the threshold fallback: changes which citations are verified (removes CRIT-01 but may under-verify more)

**Phase 7 impact:** The `_bm25_weight` and `_threshold` defaults are per-instance (set from config at construction time). Concurrent requests with different configs would each build their own retriever instance — correct behaviour, but building a new `TfidfVectorizer` and `BM25Okapi` for each citation check adds latency.

---

### `lexagent/tools/chunker.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `retriever.py` (`from_findings` builds chunks), `raptor_summarizer.py` (`build_tree_from_findings`) |
| Tests | `tests/test_chunker.py` (186 lines, good structural tests) |

**What breaks if this module changes:**
- Changing `Chunk` dataclass: breaks `retriever.py` (accesses `.source_doc`, `.chunk_index`, `.chunk_text`, `.parent_text`) and `raptor_summarizer.py`
- Changing `_approx_tokens()` to real tokeniser: changes chunk sizes; may alter retrieval quality

---

### `lexagent/tools/kanoon.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | LOW (isolated by stub) |
| Dependents | `research.py` (imported via `search_and_fetch`) |
| Tests | `tests/test_kanoon.py` (tests likely use stub; browser tests not in standard test run) |

**What breaks if this module changes:**
- Changing result dict keys (`full_text`, `header`, `citations_found`): breaks `research.py:_extract_statutes()` and chunker in cite/RAPTOR
- IndianKanoon DOM changes: will break all `await page.wait_for_selector(".result_title")` calls silently — no monitoring or fallback

---

### `lexagent/tools/legal_kg.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | LOW |
| Dependents | `research.py` (when `graphrag_enabled=True`); `save_entity_graph()` called by nobody in the graph |
| Tests | `tests/test_legal_kg.py` (181 lines) |

**What breaks if this module changes:**
- `entity_graph` dict structure change: `research.py` stores it in state; nothing else reads it from state in the current graph
- `save_entity_graph()` is never called from within the graph — the entity graph is stored in state but never persisted to SQLite during a normal run

---

### `lexagent/memory/soul.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | MEDIUM |
| Dependents | `intake.py` (`load_soul()`), `draft.py` (`build_system_prompt_blocks()`), `cli.py` (`soul_path()`, `run_setup_wizard()`) |
| Tests | `tests/test_memory.py` (403 lines, covers soul read/write) |

**What breaks if this module changes:**
- Changing `SOUL_TEMPLATE` field names: breaks `_parse_soul()` regex extraction; all `soul.get("name")` calls return empty string
- Changing `soul_path()`: breaks cli.py's "no profile" warning check

---

### `lexagent/memory/session_store.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | LOW |
| Dependents | `cli.py` (`save_session`, `get_session_state`, `search_sessions`) |
| Tests | `tests/test_memory.py` (covers session_store) |

**What breaks if this module changes:**
- Adding a column to `sessions` table: requires migration; existing databases missing the column will cause `OperationalError`
- Changing FTS5 column list: changes what is full-text searchable

---

### `lexagent/skills/loader.py`

| Attribute | Value |
|-----------|-------|
| Blast radius | LOW |
| Dependents | `intake.py` (`load_skill()`) |
| Tests | `tests/test_skills.py` (220 lines) |

**What breaks if this module changes:**
- Changing frontmatter key names (`trigger_keywords`, `matter_types`): all three bundled skill files must be updated
- Removing the two-directory merge: user skills override stops working

---

## Phase 6 Feature Flags: What Breaks if Toggled

| Flag | ON | OFF |
|------|-----|-----|
| `LEX_RAPTOR_ENABLED=true` | Research node crashes with `KeyError: 'relevance'` when draft reads RAPTOR entries (CRIT-02) | Default; no impact |
| `LEX_GRAPHRAG_ENABLED=true` | `entity_graph` populated in state; but `save_entity_graph()` never called — silently not persisted | Default; no impact |
| `LEX_RERANKER_ENABLED=true` | Flag is never read; zero effect | Default; no impact |
| `LEX_PDF_OCR_FALLBACK=true` | Flag is never read in chunker; zero effect | Default; no impact |
| `LEX_QUERY_EXPANSION=false` | BM25 queries not expanded; citation-string matching degrades for abbreviation variants | Default is `True` (on) |
| `LEX_AUTO_VERIFY_CITATIONS=false` | Graph skips cite node entirely; all citations unverified; no grounded_citations; no .docx citation appendix | Cite node runs |
| `LEX_KANOON_BACKEND=playwright` | Real browser scraping; requires Chrome/Chromium installed; adds 10–30s to research | Default `"stub"`: 1 fake result |

---

## Critical Path

The minimum set of components that must work for a basic `lex draft "test"` to succeed:

```
cli.py:_blank_state()
    → graph.py:build_graph()
        → intake.run()                    # LLM call #1
            → nodes/_llm.py:get_llm()
            → memory/soul.py:load_soul()  # returns None if SOUL.md absent (OK)
            → skills/loader.py:load_skill()
        → research.run()                  # LLM call: 0 (stub mode)
            → tools/limitation.py:check_limitation()
        → draft.run()                     # LLM call #2
            → nodes/_llm.py:get_llm() or litellm.acompletion()
            → prompts/base_system.md (non-Anthropic path)
        → [conditional: cite if findings]
        → review.run()                    # No LLM call
    → cli.py:_save_session_and_memory()
        → memory/session_store.py:save_session()
        → memory/matter_memory.py:save_matter_memory()
```

**Minimum dependencies for critical path:**
- `langgraph`, `langchain-core`, `langchain-community`, `litellm` (LLM layer)
- `pydantic-settings` (config)
- `typer`, `rich` (CLI)
- `pyyaml` (skills loader)
- `rank_bm25`, `scikit-learn`, `numpy` (retriever — only if cite runs)
- `python-docx` (review — only if `--output` used)

**Components NOT on the critical path (safe to break without killing basic use):**
- `tools/kanoon.py` (stub mode bypasses it)
- `tools/reranker.py` (never called)
- `tools/raptor_summarizer.py` (flag off by default)
- `tools/legal_kg.py` (flag off by default)
- `tools/query_expander.py:weight_terms()` (dead code)
- `memory/soul.py:append_soul_note()` (dead code)
- `prompts/tool_guidance.md` (never loaded)

---

## Tests Not Covering Critical Path Components

| Component | Test File | Coverage Assessment |
|-----------|-----------|---------------------|
| `nodes/intake.py` | None | ZERO COVERAGE — the node with the LLM call and JSON parse logic |
| `nodes/draft.py` | None | ZERO COVERAGE — the core document generation node |
| `graph.py` routing logic | None | ZERO COVERAGE — `route_after_intake`, `route_after_draft` not tested |
| `cli.py:_run_draft()` | None | ZERO COVERAGE — the full interactive loop |
| `nodes/_llm.py:get_llm()` | `tests/test_caching.py` | Partial — caching setup tested; `get_llm()` construction not |
| `memory/soul.py` | `tests/test_memory.py` | Good |
| `nodes/review.py` | `tests/test_review.py` | Good |
| `nodes/research.py` | `tests/test_research.py` | Good (stub only) |
| `nodes/cite.py` | `tests/test_cite.py` | Good |
| `tools/retriever.py` | `tests/test_retriever.py` | Good |
| `tools/chunker.py` | `tests/test_chunker.py` | Good |
| `tools/legal_kg.py` | `tests/test_legal_kg.py` | Good |
| `tools/raptor_summarizer.py` | `tests/test_raptor_summarizer.py` | Good |
| `tools/reranker.py` | `tests/test_reranker.py` | Module tested; never tested end-to-end in graph |
| `skills/loader.py` | `tests/test_skills.py` | Good |
