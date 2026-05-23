# LexAgent Issues Report

**Analysis date:** 2026-05-18
**Phase coverage:** Phases 1–6 (complete)

---

## CRITICAL Issues

These are defects that can produce incorrect or misleading output reaching a lawyer without warning.

---

### CRIT-01: Threshold bypass verifies citations against wrong chunks

| Field | Value |
|-------|-------|
| Category | Hallucination risk |
| Location | `lexagent/tools/retriever.py` lines 145–151 |
| Severity | CRITICAL |

**Description:**
When no chunk exceeds the similarity threshold (`LEX_SIMILARITY_THRESHOLD=0.35`), the retriever falls back to returning the top-k results anyway, without any threshold. In `cite.py` line 114, `if results:` evaluates to True, so the citation gets `verified=True` and a `chunk_id` even if the best chunk score is 0.001.

**Code:**
```python
indices = np.where(fused >= self._threshold)[0]
if len(indices) == 0:
    # WHY: Fall back to top_k without threshold when nothing passes —
    # better to return weak matches than nothing in the cite node.
    indices = np.argsort(fused)[::-1][:top_k]
```

**Impact:**
A citation invented by the LLM can be marked `verified=True` with a chunk reference pointing to a completely unrelated chunk. The review node sees `citations_verified=True` and `unverified_citations=None`. The lawyer gets no warning. The .docx Citations appendix shows `[✓ Grounded]` for a hallucinated case.

**Suggested fix:**
In `cite.py`, check the score of the returned result before marking verified:
```python
if results and results[0].score >= cfg.retriever_similarity_threshold:
    # mark verified
else:
    unverified.append(cite)
```

---

### CRIT-02: RAPTOR synthetic entries appear as "Verified case law" in draft

| Field | Value |
|-------|-------|
| Category | Hallucination risk |
| Location | `lexagent/nodes/draft.py` lines 156–163 + `lexagent/tools/raptor_summarizer.py` lines 188–207 |
| Severity | CRITICAL |

**Description:**
`raptor_tree_to_findings()` returns dicts with `citation=None` and `case_name="RAPTOR Summary (layer N)"`. These are appended to `research_findings`. The draft node iterates all research findings and presents them as "Verified case law to use":

```python
instruction += "Verified case law to use:\n" + "\n".join(
    f"- {r['case_name']} ({r['citation']}): {r['relevance']}" for r in research
)
```

RAPTOR entries will appear as `"- RAPTOR Summary (layer 1) (None): ..."` — missing a `relevance` key entirely (RAPTOR dicts have `snippet` not `relevance`), which causes a `KeyError` at runtime when RAPTOR is enabled and the finding was a RAPTOR node.

**Impact:**
When `LEX_RAPTOR_ENABLED=true`, draft node crashes with `KeyError: 'relevance'` for RAPTOR entries. If somehow not crashing, the LLM sees pseudo-citations with `citation=None` labelled as verified.

**Suggested fix:**
Filter RAPTOR entries from the "Verified case law" injection, or handle them separately as doctrinal context. Also add `.get("relevance", r.get("snippet", ""))` as a safe fallback.

---

### CRIT-03: Matter memory from MEMORY.md is never injected into drafts

| Field | Value |
|-------|-------|
| Category | Dead code path / silent feature failure |
| Location | `lexagent/nodes/draft.py` lines 196–199 |
| Severity | CRITICAL |

**Description:**
The infrastructure for injecting matter memory into the draft exists (`inject_memory_into_user_turn()`, the `<memory-context>` XML tag pattern), but the actual memory is never loaded and passed. Line 197 assigns `matter_memory = state.get("lawyer_soul", {})` (a misnaming), and line 199 calls `inject_memory_into_user_turn(draft_instruction, None)` — always passing `None`.

The `load_matter_memory()` function exists in `memory/matter_memory.py` and `MEMORY.md` files are written, but they are never read into state before the draft node runs.

**Code (draft.py lines 196–199):**
```python
matter_memory = state.get("lawyer_soul", {})
# Phase 5 will add real RAG context here; for now pass None
draft_instruction = inject_memory_into_user_turn(draft_instruction, None)
```

**Impact:**
`lex draft --matter-id M001` resumes a matter (state fields restored), but prior session notes and summaries in MEMORY.md are never given to the draft LLM. The "memory system" described in CLAUDE.md is partially non-functional.

**Suggested fix:**
In `cli.py` or the draft node, load MEMORY.md for the current `matter_id` and pass it to `inject_memory_into_user_turn()`.

---

## HIGH Issues

---

### HIGH-01: LLM reranker is dead code

| Field | Value |
|-------|-------|
| Category | Dead code |
| Location | `lexagent/tools/reranker.py`, `lexagent/tools/retriever.py:retrieve_reranked()`, `lexagent/config.py:reranker_enabled` |
| Severity | HIGH |

**Description:**
`LexConfig.reranker_enabled` is defined and documented. `HybridRetriever.retrieve_reranked()` is implemented. `LLMReranker` is a complete class. But `reranker_enabled` is never read in the graph code. `retrieve_reranked()` is never called. The cite node always calls `retriever.retrieve(cite, top_k=1)` synchronously.

**Impact:**
Setting `LEX_RERANKER_ENABLED=true` has zero effect. A lawyer enabling it expects improved citation quality but gets none. 245 tests pass without ever exercising the re-ranker in an end-to-end graph scenario.

**Suggested fix:**
In `cite.py`, check `cfg.reranker_enabled` and use `retrieve_reranked()` when True. Requires making the cite node's inner loop `async` properly.

---

### HIGH-02: `pdf_ocr_fallback` config flag is a stub — no OCR implementation

| Field | Value |
|-------|-------|
| Category | Dead code / missing implementation |
| Location | `lexagent/config.py` line 89, `lexagent/tools/chunker.py:_extract_pdf_text()` |
| Severity | HIGH |

**Description:**
`LexConfig.pdf_ocr_fallback` is documented as enabling Tesseract OCR for scanned PDFs. The chunker's `_extract_pdf_text()` uses pdfplumber regardless of this flag. There is no `if config.pdf_ocr_fallback` branch. Setting `LEX_PDF_OCR_FALLBACK=true` does nothing. Scanned PDFs (common in Indian courts — old judgments, certified copies) will produce empty text silently.

**Suggested fix:**
Add an OCR fallback path: if pdfplumber returns less than a threshold of text per page, attempt `pytesseract.image_to_string()` on the page image.

---

### HIGH-03: `weight_terms()` function is dead code

| Field | Value |
|-------|-------|
| Category | Dead code |
| Location | `lexagent/tools/query_expander.py:weight_terms()` lines 141–149 |
| Severity | HIGH |

**Description:**
`weight_terms()` computes IDF-style weights for query terms and is documented as usable for BM25 score multiplication. It is never called anywhere in the codebase. The `_TERM_WEIGHTS` dict it relies on is also unused.

**Suggested fix:**
Either remove `weight_terms()` and `_TERM_WEIGHTS`, or wire it into `HybridRetriever._bm25_scores()` to multiply per-term weights into the BM25 scoring.

---

### HIGH-04: `cause_of_action_date` field read but not in LexState

| Field | Value |
|-------|-------|
| Category | Weak abstraction / silent failure |
| Location | `lexagent/nodes/research.py` lines 90–93 |
| Severity | HIGH |

**Description:**
The research node calls:
```python
coa_date = state.get("cause_of_action_date") or ""
limitation_result = check_limitation(
    matter_type=state.get("matter_type") or "",
    cause_of_action_date=coa_date if isinstance(coa_date, str) else "",
)
```
`"cause_of_action_date"` is not a field in `LexState` (state.py). `state.get("cause_of_action_date")` always returns `None`, so the limitation check always runs without a date, always returning `risk="unknown"` instead of a real deadline/risk assessment.

The intake node never asks for or stores `cause_of_action_date`. The limitation check is therefore permanently operating in "no date provided" mode.

**Suggested fix:**
Add `cause_of_action_date: Optional[str]` to `LexState`. Add it to `_blank_state()` in cli.py. Add a question for it in `INTAKE_SYSTEM_PROMPT` when the matter type is limitation-sensitive.

---

### HIGH-05: Intake prompt is inline string, not in prompts/ directory

| Field | Value |
|-------|-------|
| Category | Tight coupling / violates project code rule |
| Location | `lexagent/nodes/intake.py` lines 22–48 |
| Severity | HIGH |

**Description:**
`INTAKE_SYSTEM_PROMPT` is a 26-line prompt string hardcoded in `intake.py`. CLAUDE.md Code Rule 4 explicitly states: "All system prompts in `lexagent/prompts/` — never inline strings." `tool_guidance.md` is also never used (it is in `prompts/` but never read by any node).

**Impact:**
Non-engineers cannot edit the intake prompt without touching Python code. The intake questions cannot be versioned independently. This will bite during Phase 7 (Telegram — different intake flow requirements).

**Suggested fix:**
Move `INTAKE_SYSTEM_PROMPT` to `lexagent/prompts/intake_system.md`. Use `_load_prompt("intake_system.md")` to load it (reuse the pattern from draft.py).

---

### HIGH-06: `tool_guidance.md` prompt is never injected

| Field | Value |
|-------|-------|
| Category | Dead code / missing implementation |
| Location | `lexagent/prompts/tool_guidance.md` |
| Severity | HIGH |

**Description:**
`lexagent/prompts/tool_guidance.md` contains tool usage instructions (search_kanoon, verify_citation, calculate_limitation). It is never loaded or injected into any prompt. The draft node loads only `base_system.md`.

**Impact:**
The LLM is told (via `base_system.md`) that it has tools available and must use them, but never receives the tool guidance. The tools described in `tool_guidance.md` (`search_ecourts`, `search_courtlistener`, `verify_citation`) are not even implemented — they are placeholders for future tools. The prompt creates a contradiction: it tells the LLM it has tools that don't exist.

**Suggested fix:**
Either inject `tool_guidance.md` only when tools are actually bound via `bind_tools()` (which currently never happens), or remove the file and the tool references until Phase 4+ tools are implemented.

---

### HIGH-07: `get_langchain_tools()` / `bind_tools()` are never used

| Field | Value |
|-------|-------|
| Category | Dead code |
| Location | `lexagent/tools/registry.py:get_langchain_tools()` lines 37–54 |
| Severity | HIGH |

**Description:**
`ToolRegistry.get_langchain_tools()` is implemented and documented with `# LANGGRAPH: bind_tools()` comment. `bind_tools()` is never called. No node in the graph receives a tool-calling LLM. The LLM is never told it can call tools. This means the LangGraph tool-calling pattern is entirely absent — the agent cannot autonomously decide to run a limitation check or search Kanoon. These are hardcoded sequential operations in the node functions instead.

**Suggested fix:**
For Phase 7 (Telegram), consider whether to implement a proper tool-calling agent loop using `bind_tools()` or keep the current sequential node approach. If keeping sequential, remove `get_langchain_tools()` to avoid misleading the codebase.

---

## MEDIUM Issues

---

### MED-01: LexConfig instantiated inside routing function on every call

| Field | Value |
|-------|-------|
| Category | Performance / scalability |
| Location | `lexagent/graph.py` lines 50–51 (`route_after_draft`) |

**Description:**
```python
def route_after_draft(state: LexState) -> str:
    ...
    config = LexConfig()  # new instance every call
```
`LexConfig` is a Pydantic `BaseSettings` which reads environment variables and `.env` files on every instantiation. This is called synchronously inside the routing function which runs on every graph invocation. Under load (Phase 7: Telegram with multiple concurrent users), this adds unnecessary overhead.

**Suggested fix:**
Instantiate `LexConfig` once at graph build time or at module level and pass it through the routing closure.

---

### MED-02: Blocking I/O and CPU in async context

| Field | Value |
|-------|-------|
| Category | Bottleneck / async correctness |
| Location | `lexagent/nodes/cite.py` (HybridRetriever calls), `lexagent/nodes/review.py` (write_docx) |

**Description:**
Both `cite.run()` and `review.run()` are declared `async def` but contain synchronous blocking operations:
- `retriever.retrieve()` runs BM25 and numpy/sklearn computations synchronously
- `write_docx()` does synchronous file I/O (python-docx disk write)

These block the event loop. For Phase 7 (Telegram), concurrent requests will queue behind each other at these points.

**Suggested fix:**
Wrap CPU-bound operations in `await asyncio.get_event_loop().run_in_executor(None, ...)`. For file I/O, use `aiofiles` or `run_in_executor`.

---

### MED-03: `_LEGAL_SYNONYMS` has a duplicate key (silent data bug)

| Field | Value |
|-------|-------|
| Category | Data bug |
| Location | `lexagent/tools/query_expander.py` lines 27 and 35 |

**Description:**
```python
"respondent": ["defendant", "opposite party", "non-applicant"],   # line 27
...
"respondent": ["appellee", "defendant", "opposite party"],        # line 35
```
Python silently overwrites the first with the second. The `"non-applicant"` synonym is lost. Tests for query expansion would not catch this unless they specifically test "non-applicant" expansion.

**Suggested fix:**
Remove the duplicate key. Merge the synonym lists into one entry.

---

### MED-04: LiteLLM disk cache never expires — unbounded disk growth

| Field | Value |
|-------|-------|
| Category | Scalability |
| Location | `lexagent/nodes/_llm.py:setup_litellm_cache()` lines 50–69 |

**Description:**
`litellm.Cache(type="disk", disk_cache_dir=str(cache_dir))` creates a disk cache with no TTL or size limit. Over time this will grow without bound. A busy lawyer running 100+ matters per year will accumulate gigabytes of cached LLM responses, including sensitive client data.

**Suggested fix:**
Pass `ttl=604800` (7 days) to `litellm.Cache()`. Add a periodic cleanup cron or a `lex cache clear` command.

---

### MED-05: Kanoon scraper opens a new browser for every research call

| Field | Value |
|-------|-------|
| Category | Bottleneck / scalability |
| Location | `lexagent/tools/kanoon.py:search_and_fetch()` lines 191–218 |

**Description:**
`async_playwright()` launches a new Chrome instance per `search_and_fetch()` call. This takes 2–4 seconds for browser startup. It also means no cookie persistence or session reuse across Kanoon searches.

For Phase 7 (Telegram with concurrent users), a new Chrome instance per request will consume significant memory and CPU.

**Suggested fix:**
Consider a persistent browser context singleton. Alternatively, implement the Kanoon API backend mode (`kanoon_backend="api"`) using the Indian Kanoon REST API (no browser needed).

---

### MED-06: `docx_path` is overwritten to `None` by review node when no file is written

| Field | Value |
|-------|-------|
| Category | State mutation side effect |
| Location | `lexagent/nodes/review.py` lines 88–92 |

**Description:**
The review node always returns `"docx_path": docx_path_out` where `docx_path_out` starts as `None`. If the path was set in state but `draft.strip()` was empty, `docx_path_out` stays `None` and the original `docx_path` (user's requested output path) is overwritten with `None`. The CLI then shows no "Saved:" panel even though the user explicitly requested `--output draft.docx`.

**Suggested fix:**
Only include `"docx_path"` in the returned dict when a file was actually written:
```python
result = {"risk_annotations": ...}
if docx_path_out:
    result["docx_path"] = docx_path_out
return result
```

---

### MED-07: Session state continuation does not restore Phase 6 fields

| Field | Value |
|-------|-------|
| Category | State completeness |
| Location | `lexagent/cli.py` lines 143–159 |

**Description:**
When continuing a matter with `--matter-id`, `cli.py` resets `grounded_citations`, `retrieval_chunks`, and `docx_path` to `None` but does NOT reset `raptor_tree` or `entity_graph`. These Phase 6 fields (potentially large dicts) persist from the prior session into the new run. The research node only sets them when the relevant flags are enabled, so they may be stale from a run where RAPTOR/GraphRAG was enabled but is now disabled.

**Suggested fix:**
Reset `raptor_tree` and `entity_graph` to `None` in the prior-state resume block alongside the other resets.

---

### MED-08: Skills system: bundled skills are only Indian-law scoped but no jurisdiction gate

| Field | Value |
|-------|-------|
| Category | Logic gap |
| Location | `lexagent/skills/loader.py`, all three bundled `.md` skills |

**Description:**
All three bundled skills have `jurisdiction: [Indian courts - all]` in their frontmatter, but `load_skill()` does not check jurisdiction when matching. A `matter_type="injunction"` for a UK High Court matter would receive the Indian civil litigation skill with CPC-specific templates and Indian citation mandates.

**Suggested fix:**
Add jurisdiction filtering to `load_skill()`: if `state["jurisdiction_country"]` is set and the skill has a `jurisdiction` list, only match skills whose jurisdiction includes the country code.

---

### MED-09: SQLite connections are not pooled

| Field | Value |
|-------|-------|
| Category | Scalability |
| Location | `lexagent/memory/session_store.py`, `lexagent/tools/legal_kg.py` |

**Description:**
Every database operation opens and closes a new `sqlite3.connect()`. For the current single-user CLI this is fine, but for Phase 7 (Telegram with concurrent users), SQLite write contention will cause `OperationalError: database is locked`.

**Suggested fix:**
For Phase 7, evaluate migrating to a WAL-mode SQLite (`PRAGMA journal_mode=WAL`) at minimum, or moving to PostgreSQL via Prisma (already used in the `lexanodes/` project in the same repo).

---

## LOW Issues

---

### LOW-01: `_blank_state()` in cli.py missing Phase 6 fields

| Field | Value |
|-------|-------|
| Category | State completeness |
| Location | `lexagent/cli.py:_blank_state()` lines 226–260 |

**Description:**
`_blank_state()` does not initialise `raptor_tree` or `entity_graph` (both added in Phase 6 to `LexState`). TypedDict does not enforce initialisation, but accessing these via `state.get()` will return `None` correctly. However, serialisation in `matter_memory._save_state_snapshot()` will also exclude them when they are genuinely `None`, which is correct. This is a cosmetic inconsistency rather than a bug.

**Suggested fix:**
Add `"raptor_tree": None, "entity_graph": None` to `_blank_state()` for completeness.

---

### LOW-02: `test_state.py` minimal state dict missing Phase 6 fields

| Field | Value |
|-------|-------|
| Category | Test coverage |
| Location | `tests/test_state.py:_minimal_state()` lines 13–43 |

**Description:**
`_minimal_state()` doesn't include `raptor_tree`, `entity_graph`, `grounded_citations`, `retrieval_chunks`, or `docx_path`. Tests validating "all optional fields are None" will pass but won't cover the Phase 5/6 fields.

---

### LOW-03: `base_system.md` has `{active_skill_section}` placeholder but it's always empty

| Field | Value |
|-------|-------|
| Category | Dead template variable |
| Location | `lexagent/prompts/base_system.md` line 22, `lexagent/nodes/draft.py` line 131 |

**Description:**
`base_system.md` has `{active_skill_section}` as a placeholder. In `_build_string_system_prompt()`, this is replaced with `""` (empty string). The skill content is included via `{lawyer_soul_section}` (which calls `build_system_prompt_blocks()` that combines soul + skill into a single section). So `{active_skill_section}` is always empty and the placeholder exists as dead template variable.

---

### LOW-04: Rich emoji in docx metadata footer

| Field | Value |
|-------|-------|
| Category | Court filing risk |
| Location | `lexagent/tools/docx_writer.py` line 102 |

**Description:**
The metadata footer `"Generated by LexAgent | Phase 5 draft — verify citations before filing"` is acceptable, but line 333 in cli.py uses emoji (`⚖`, `📄`) in panel titles. If a lawyer copies the draft output directly (not via .docx), emoji characters may appear in submitted documents. The `.docx` footer itself does not contain emoji, so this is low risk.

---

### LOW-05: `save_session` calls `init_db` on every save

| Field | Value |
|-------|-------|
| Category | Unnecessary overhead |
| Location | `lexagent/memory/session_store.py` line 114 |

**Description:**
`save_session()` calls `init_db()` defensively on every call. `init_db()` runs 5 `CREATE IF NOT EXISTS` statements on every save. This is harmless but wasteful.

---

## Dead Code Inventory

| Item | Location | Notes |
|------|----------|-------|
| `LLMReranker` class | `tools/reranker.py` | Complete implementation; `reranker_enabled` flag never checked in graph |
| `HybridRetriever.retrieve_reranked()` | `tools/retriever.py` lines 166–184 | Never called |
| `weight_terms()` | `tools/query_expander.py` lines 141–149 | Never called |
| `_TERM_WEIGHTS` dict | `tools/query_expander.py` lines 91–110 | Only referenced by `weight_terms()` |
| `ToolRegistry.get_langchain_tools()` | `tools/registry.py` lines 37–54 | Never called; `bind_tools()` never invoked |
| `tool_guidance.md` | `lexagent/prompts/tool_guidance.md` | Never loaded by any node |
| `{active_skill_section}` placeholder | `lexagent/prompts/base_system.md` line 22 | Always replaced with `""` |
| `append_soul_note()` | `memory/soul.py` lines 104–123 | "self-learning loop (Phase 6)" — not called anywhere |
| `cause_of_action_date` state access | `nodes/research.py` lines 90–93 | Field not in LexState; always None |
| `inject_memory_into_user_turn()` | `nodes/draft.py` lines 23–37 | Function called but always with `None` as second argument |
| `matter_memory` variable in draft.py | `nodes/draft.py` lines 196–199 | Misnamed variable assigned `lawyer_soul`, not used meaningfully |

---

## Tight Coupling Inventory

| Coupling | Location | Description |
|----------|----------|-------------|
| Intake prompt is inlined, not in prompts/ | `nodes/intake.py` lines 22–48 | Violates CLAUDE.md rule 4 |
| `check_limitation` imported by name in research node | `nodes/research.py` line 89 | `ToolRegistry.get("check_limitation")` — couples research node to exact tool name string |
| `HybridRetriever` instantiated inline in cite node | `nodes/cite.py` line 97 | Imports and constructs retriever inside the node; no dependency injection |
| `LegalKnowledgeGraph` instantiated inline in research node | `nodes/research.py` line 139 | No abstraction layer; directly coupled to the KG implementation |
| `route_after_draft` reads `LexConfig()` | `graph.py` line 50 | Config instantiated inside routing function, not injected |
| `kanoon.py` has module-level `config = LexConfig()` | `tools/kanoon.py` line 21 | Config read at import time; tests cannot override `kanoon_headless` without monkeypatching |
| `docx_writer.py` accepts full `LexState` | `tools/docx_writer.py` line 24 | Writer reads multiple state fields directly; tightly coupled to state structure |
