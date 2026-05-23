# LexAgent Execution Graph

**Source:** `lexagent/graph.py`
**Graph type:** `langgraph.graph.StateGraph(LexState)`

---

## Node-by-Node Breakdown

### Node: `intake`

| Attribute | Value |
|-----------|-------|
| File | `lexagent/nodes/intake.py` |
| Function | `async def run(state: LexState) -> dict` |
| Entry point | Yes (`graph.set_entry_point("intake")`) |

**State consumed (reads):**
- `user_input` — original matter brief
- `messages` — full conversation history
- `matter_type`, `parties`, `jurisdiction`, `purpose` — presence check via `_all_fields_present()`
- `lawyer_soul` — if present, skips reload; if absent, calls `load_soul()`

**State written (partial dict returned):**
- `matter_type` — extracted by LLM
- `parties` — extracted by LLM
- `jurisdiction` — extracted by LLM
- `purpose` — extracted by LLM
- `clarifying_questions` — list of pending questions
- `intake_complete` — True when all 4 required fields are present
- `messages` — appended with new AIMessage
- `lawyer_soul` — loaded from SOUL.md if not already in state
- `active_skill` — loaded from `skills/loader.py` if `matter_type` was extracted
- `error` — set on exception

**Tools used:** None directly. Calls `skills/loader.py:load_skill()` and `memory/soul.py:load_soul()`.

**Prompts used:**
- `INTAKE_SYSTEM_PROMPT` — inlined string in `nodes/intake.py` (lines 22-48), NOT in `prompts/`

**LLM call:** Yes — `get_llm(config).ainvoke(messages)` with system + user + history messages.

**Key logic:**
- Short-circuit on line 62: if `_all_fields_present(state)` is True at entry, returns `{"intake_complete": True}` immediately without an LLM call.
- After LLM response, checks again on line 127 after merging extracted fields.
- Falls back to `{"clarifying_questions": ["Could you describe..."]}` if JSON parse fails.

---

### Node: `research`

| Attribute | Value |
|-----------|-------|
| File | `lexagent/nodes/research.py` |
| Function | `async def run(state: LexState) -> dict` |

**State consumed (reads):**
- `matter_type`, `purpose`, `jurisdiction` — query construction
- `user_input` — fallback if no intake fields
- `cause_of_action_date` — passed to limitation tool (NOTE: this field is NOT in `LexState`; `state.get()` returns None silently)

**State written:**
- `research_findings` — list of dicts `{title, url, snippet, full_text, citations_found, status}`; if RAPTOR enabled, synthetic summary dicts are appended
- `statutes_cited` — up to 15 statute strings extracted by regex from fetched texts
- `limitation_analysis` — human-readable limitation analysis string
- `raptor_tree` — (optional, `raptor_enabled=True`) list of `{layer, text, source_chunks}` dicts
- `entity_graph` — (optional, `graphrag_enabled=True`) `{entities: [...], edges: [...]}` dict
- `error` — set on exception

**Tools used:**
- `tools/kanoon.py:search_and_fetch()` — when `config.kanoon_backend != "stub"`
- `ToolRegistry.get("check_limitation")` — always called via registry
- `tools/raptor_summarizer.py:RaptorSummarizer` — when `config.raptor_enabled=True`
- `tools/legal_kg.py:LegalKnowledgeGraph` — when `config.graphrag_enabled=True`

**Prompts used:** None directly. RAPTOR summarizer uses inline prompts.

**LLM calls:**
- No direct LLM call in base path
- If `raptor_enabled=True`: one LLM call per cluster via `RaptorSummarizer._summarize_cluster()`
- If `reranker_enabled` (see note below): NOT called in research; reranker is available but unused here

---

### Node: `draft`

| Attribute | Value |
|-----------|-------|
| File | `lexagent/nodes/draft.py` |
| Function | `async def run(state: LexState) -> dict` |

**State consumed (reads):**
- `matter_type`, `parties`, `jurisdiction`, `purpose` — injected into system prompt and user turn
- `key_clauses`, `tone_preference` — optional additions to user-turn instruction
- `research_findings` — injected as "Verified case law to use" if present
- `lawyer_soul` — injected via `build_system_prompt_blocks()` as system content
- `active_skill` — injected via `build_system_prompt_blocks()` as system content

**State written:**
- `draft_output` — full LLM output (document text + plain English summary mixed together)
- `plain_english_summary` — extracted from `draft_output` via regex
- `messages` — appended with AIMessage containing full draft
- `error` — set on exception

**Tools used:** None.

**Prompts used:**
- `lexagent/prompts/base_system.md` — used as system prompt for non-Anthropic path (loaded by `_load_prompt("base_system.md")`)
- For Anthropic path: `SOUL.md + skill content` assembled by `build_system_prompt_blocks()` into cache_control blocks
- IMPORTANT: `lexagent/prompts/tool_guidance.md` is **NOT injected** by the draft node

**LLM calls:**
- Anthropic path (`config.model_provider == "anthropic"` and `enable_prompt_caching=True`): `litellm.acompletion()` with `cache_control` blocks
- All other providers: `ChatLiteLLM().ainvoke(messages)` via `get_llm(config)`

**Key implementation note:**
- Line 197: `matter_memory = state.get("lawyer_soul", {})` — this variable is named `matter_memory` but it is actually loading `lawyer_soul`. The intent was to pass real matter memory (from MEMORY.md) into `inject_memory_into_user_turn()`, but `None` is passed instead (line 199). **This is a dead code path — matter memory from MEMORY.md is never injected into the draft despite the infrastructure for it existing.**

---

### Node: `cite`

| Attribute | Value |
|-----------|-------|
| File | `lexagent/nodes/cite.py` |
| Function | `async def run(state: LexState) -> dict` |

**State consumed (reads):**
- `draft_output` — citation strings extracted via `_CITATION_RE`
- `research_findings` — corpus for hybrid retrieval
- Config (via `LexConfig()` instantiated inside the node)

**State written:**
- `citations_verified` — True only when all citations get a chunk match
- `unverified_citations` — list of citation strings without chunk match (None if all verified)
- `grounded_citations` — list of `{chunk_id, source, paragraph_ref, verified, score}`
- `retrieval_chunks` — list of `{chunk_id, child_text, parent_text, source_doc, section_id, bm25_score, vector_score}`
- `error` — set on exception

**Tools used:**
- `tools/retriever.py:HybridRetriever.from_findings()` — built from `research_findings`
- `HybridRetriever.retrieve(cite, top_k=1)` — for each citation string

**Prompts used:** None.

**LLM calls:** None. (LLM reranker is available via `retrieve_reranked()` but **not called in the cite node** — it uses synchronous `retrieve()` only.)

**Key logic:**
- If `raw == []` (no citations in draft): immediately returns `citations_verified=True, grounded_citations=[], retrieval_chunks=[]`
- If `findings` is non-empty: uses `HybridRetriever` (Phase 5 path)
- If `findings` is empty: falls back to substring search against corpus (Phase 4 fallback path)
- The threshold fallback (line 148-149 of retriever.py): when nothing passes the similarity threshold, returns top_k without threshold filtering — this can return low-quality matches to cite with `verified=True`

---

### Node: `review`

| Attribute | Value |
|-----------|-------|
| File | `lexagent/nodes/review.py` |
| Function | `async def run(state: LexState) -> dict` |

**State consumed (reads):**
- `draft_output` — word count check
- `unverified_citations` — citation grounding check
- `grounded_citations` — passed through to docx_writer
- `matter_type` — word limit lookup
- `docx_path` — if set, triggers docx_writer

**State written:**
- `docx_path` — updated to absolute path if .docx was written; None if not
- `risk_annotations` — list of `{clause: "review", risk_level: "M", note: issue_text}` if any issues; None if all clear
- `error` — set on exception

**Tools used:**
- `tools/docx_writer.py:write_docx()` — only when `docx_path` is not None

**Prompts used:** None.

**LLM calls:** None.

**Key logic:**
- Issues are non-blocking: review surfaces them as `risk_annotations` but does NOT set `error` or stop the graph.
- `docx_path` is overwritten to `None` implicitly when `write_docx` is not called (the returned dict has `"docx_path": None` — this overwrites any existing `docx_path` that was set).

---

## Conditional Edge Table

| Source Node | Condition | Target Node |
|-------------|-----------|-------------|
| `intake` | `state.get("error")` | `END` |
| `intake` | `state.get("intake_complete") == True` | `research` |
| `intake` | (neither) | `intake` (loop back) |
| `draft` | `state.get("error")` | `END` |
| `draft` | `config.auto_verify_citations=True AND state.get("research_findings")` | `cite` |
| `draft` | (neither condition) | `review` |

**Note on `route_after_draft`:** `LexConfig()` is instantiated inside the routing function (graph.py line 50). This means a fresh config read happens on every routing decision — no caching of the config object between nodes.

## Fixed Edges

| Source | Target | Notes |
|--------|--------|-------|
| `research` | `draft` | Always; no branching |
| `cite` | `review` | Always |
| `review` | `END` | Terminal node |

---

## Loop and Termination Conditions

### Intake Loop

- **Loop condition:** `state.get("intake_complete") == False` AND no error
- **Routes to:** `intake` (self-loop via conditional edge)
- **Termination:** `intake_complete=True` → routes to `research`
- **External safety limit:** CLI enforces `max_intake_rounds = 5` (hardcoded in `cli.py` line 165)
- **Potential infinite loop risk:** The graph itself has no loop limit — only the CLI outer `while True` loop enforces the limit. If the graph is invoked directly (not via CLI), there is no limit.

---

## Async Patterns

| Component | Async Pattern |
|-----------|---------------|
| `intake.run()` | `async def`, `await llm.ainvoke()` |
| `research.run()` | `async def`, `await search_and_fetch()`, `await summarizer.build_tree_from_findings()` |
| `draft.run()` | `async def`, `await litellm.acompletion()` or `await llm.ainvoke()` |
| `cite.run()` | `async def` but `retriever.retrieve()` is **synchronous** inside — blocking call in async context |
| `review.run()` | `async def` but `write_docx()` is **synchronous** inside — blocking file I/O in async context |
| `kanoon.search_and_fetch()` | `async def`, full Playwright async API |
| `RaptorSummarizer.build_tree()` | `async def`, `asyncio.gather()` for concurrent cluster summarization |
| `LLMReranker.rerank()` | `async def`, `await self._score_passages()` |
| CLI | `asyncio.run(_run_draft(...))` — single event loop |
| `retrieve_reranked()` | `async def` — available but **not called anywhere** |

**Known issue:** `cite.run()` and `review.run()` are declared `async` but execute synchronous blocking operations (`retriever.retrieve()` does numpy/sklearn operations; `write_docx()` does file I/O). These block the event loop. For small inputs this is not a problem, but for large documents or many citations it will cause latency spikes.

---

## State Mutation Summary by Node

| Field | intake | research | draft | cite | review |
|-------|--------|----------|-------|------|--------|
| `user_input` | reads | reads | — | — | — |
| `matter_type` | writes | reads | reads | — | reads |
| `parties` | writes | — | reads | — | — |
| `jurisdiction` | writes | reads | reads | — | — |
| `purpose` | writes | reads | reads | — | — |
| `intake_complete` | writes | — | — | — | — |
| `clarifying_questions` | writes | — | — | — | — |
| `messages` | reads+writes | — | writes | — | — |
| `lawyer_soul` | writes | — | reads | — | — |
| `active_skill` | writes | — | reads | — | — |
| `research_findings` | — | writes | reads | reads | — |
| `statutes_cited` | — | writes | — | — | — |
| `limitation_analysis` | — | writes | — | — | — |
| `raptor_tree` | — | writes | — | — | — |
| `entity_graph` | — | writes | — | — | — |
| `draft_output` | — | — | writes | reads | reads |
| `plain_english_summary` | — | — | writes | — | — |
| `citations_verified` | — | — | — | writes | — |
| `unverified_citations` | — | — | — | writes | reads |
| `grounded_citations` | — | — | — | writes | reads |
| `retrieval_chunks` | — | — | — | writes | — |
| `docx_path` | — | — | — | — | reads+writes |
| `risk_annotations` | — | — | — | — | writes |
| `error` | writes | writes | writes | writes | writes |
