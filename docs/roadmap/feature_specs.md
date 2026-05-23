# LexAgent Feature Specifications — Phase 7–10

Every feature is specified to the level required for an engineer to start implementation
without further design discussion. All file paths are relative to `/Users/anshoosareen/Lexagent/`.

---

## A. Litigation Workflow Engine

---

### A1. Litigation Stage Tracker

**One-line description:** Tracks the procedural stage of a matter (FIR → charge sheet → cognizance → framing → trial → judgment) and surfaces the current stage in all prompts.

**Business value:** A lawyer picking up a criminal matter at mid-trial has to mentally reconstruct what stage the case is at. This field makes it explicit and drives different intake questions, different research queries (bail vs trial arguments), and different document templates.

**Engineering complexity:** M

Justification: New LexState field + new intake prompt question + new conditional routing. No new nodes needed — injected into existing skill selection logic. Medium because `matter_stage` must cascade through research query construction and skill file selection.

**New LangGraph nodes required:** None. Stage is captured in intake, used in research and draft.

**New LexState fields required:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `matter_stage` | `Optional[str]` | research, draft, intake | intake |
| `litigation_timeline` | `Optional[List[dict]]` | draft, review | intake, research |

`litigation_timeline` is a list of `{stage, date, notes}` dicts — the matter's procedural history.

**New tools required:** None. The limitation tool already handles stage-aware limitation periods once `cause_of_action_date` is fixed (HIGH-04).

**New config flags required:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_STAGE_TRACKING` | `True` | When False, intake never asks for stage |

**CRG impact radius:** MEDIUM

- `intake.py` — new questions for stage extraction
- `state.py` — 2 new fields
- `_blank_state()` in `cli.py` — needs initialization
- `research.py` — query construction uses `matter_stage` if present
- Blast radius: MEDIUM (no graph topology change)

**Retrieval changes:** Research node should vary Kanoon query based on stage (bail arguments vs trial arguments vs appeal arguments). No new index required.

**Dependencies:** HIGH-04 fix (cause_of_action_date in LexState) must land first so limitation analysis covers stage-appropriate articles.

**Rollout priority:** P1 (Phase 8)

---

### A2. Procedural Next-Step Detection

**One-line description:** After intake, the agent identifies the next required procedural step under CPC/CrPC based on the current `matter_stage` and injects it as a checklist into the draft.

**Business value:** Junior lawyers routinely miss procedural steps (framing of issues under O.XIV CPC, service requirements, vakalatnama before first appearance). This flags the immediate next required step automatically.

**Engineering complexity:** M

**New LangGraph nodes required:**

| Node | File | Inputs | Outputs |
|------|------|--------|---------|
| `procedure_check` (inline in research or new) | `lexagent/nodes/procedure_check.py` | `matter_type`, `matter_stage`, `jurisdiction` | `procedural_next_steps: List[str]` |

This can be implemented as part of the research node (additional tool call) rather than a standalone node to avoid graph topology complexity.

**New LexState fields:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `procedural_next_steps` | `Optional[List[str]]` | draft | research or new procedure_check node |

**New tools required:**

| Tool | File | Registry entry |
|------|------|---------------|
| `check_procedure` | `lexagent/tools/procedure.py` | `@ToolRegistry.register(name="check_procedure", ...)` |

The tool is a lookup table mapping `(matter_type, matter_stage)` → `[next_steps]`. Data stored as YAML under `lexagent/data/procedure_tables/`. Not an LLM call — deterministic lookup.

**New config flags:** `LEX_PROCEDURE_CHECK` (bool, default True)

**CRG impact radius:** LOW-MEDIUM

- `research.py` or new `procedure_check.py` node
- `state.py` (1 new field)
- `draft.py` (reads new field to inject into instruction)

**Dependencies:** A1 (matter_stage field must exist)

**Rollout priority:** P1 (Phase 8)

---

### A3. Limitation Deadline Alert

**One-line description:** The review node warns the lawyer if the limitation period is within 90 days or expired, based on `limitation_analysis` and `cause_of_action_date`.

**Business value:** Missing limitation bars is a professional negligence claim. The current limitation tool runs but never surfaces its output in a lawyer-visible warning — it is buried in state.

**Engineering complexity:** S

**New LangGraph nodes:** None. New check in `review.py`.

**New LexState fields:** `limitation_expiry_date: Optional[str]` (ISO date string, written by research node from limitation tool output).

**New tools:** None. Extend `check_limitation` return dict to include `expiry_date` field.

**New config flags:** `LEX_LIMITATION_ALERT_DAYS` (int, default 90)

**CRG impact radius:** LOW

- `review.py` (new check in `_collect_issues()`)
- `tools/limitation.py` (extend return schema)
- `state.py` (1 new field)

**Dependencies:** HIGH-04 fix (cause_of_action_date in LexState) is required for this to have real data.

**Rollout priority:** P0 (Phase 8, immediate business value)

---

### A4. Court Fee Calculator

**One-line description:** A tool that computes court fees based on subject matter value and jurisdiction (state), outputting the correct fee with the applicable schedule article.

**Business value:** Incorrect court fee computation is a common defect in plaints that courts use to return documents. This is a table-lookup problem that should never require LLM reasoning.

**Engineering complexity:** M

Justification: Fee schedules vary by state (Delhi Court Fees Act, Maharashtra Court Fees Act, etc.) and are updated. Data maintenance is ongoing.

**New LangGraph nodes:** None. New tool called from research node or review node.

**New LexState fields:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `court_fee_computation` | `Optional[dict]` | draft, review | research or review |

**New tools:**

| Tool | File | Data source |
|------|------|------------|
| `calculate_court_fee` | `lexagent/tools/court_fees.py` | `lexagent/data/court_fees/{state}.yaml` |

YAML schema per state: `{article, description, rate, min_fee, max_fee, base_value}`.

**New config flags:** `LEX_COURT_FEE_ENABLED` (bool, default True)

**CRG impact radius:** LOW (new tool, new YAML data files, research or review node reads result)

**Retrieval changes:** None.

**Dependencies:** A1 (matter_stage, jurisdiction must be captured). Court fee is only relevant for civil plaints.

**Rollout priority:** P2 (Phase 8)

---

### A5. Filing Checklist Generator

**One-line description:** Generates a court-specific, matter-type-specific pre-filing checklist as part of the review node output.

**Business value:** Each court has specific filing requirements (number of copies, format of index, paper size, colour of cover page). These are not LLM knowledge — they are institutional rules that change per court registry.

**Engineering complexity:** S

**New LangGraph nodes:** None. New section in review output.

**New LexState fields:** `filing_checklist: Optional[List[str]]`

**New tools:** `generate_filing_checklist` — YAML data under `lexagent/data/filing_requirements/{court_code}.yaml`.

**New config flags:** None.

**CRG impact radius:** LOW

**Rollout priority:** P2 (Phase 8)

---

## B. Hearing Preparation

---

### B1. Hearing Brief Generator

**One-line description:** A new sub-graph invoked via `lex draft --hearing-prep M001` that generates a structured hearing brief: issues list, arguments, case law, anticipated objections, and rebuttals.

**Business value:** Lawyers spend 2–4 hours preparing a hearing brief that follows a predictable structure. This automates the structure while letting the lawyer inject strategy.

**Engineering complexity:** L

Justification: New sub-graph with 3 nodes (issues extraction, argument generation, rebuttal generation). Must read from `MEMORY.md` (CRIT-03 fix required). Requires real research findings.

**New LangGraph nodes:**

| Node | File | Inputs | Outputs |
|------|------|--------|---------|
| `hearing_intake` | `lexagent/nodes/hearing_intake.py` | `matter_id`, `matter_type`, previous state | `hearing_issues`, `last_hearing_summary` |
| `hearing_draft` | `lexagent/nodes/hearing_draft.py` | `hearing_issues`, `research_findings`, `lawyer_soul` | `hearing_brief_output` |
| `hearing_review` | (reuse `review.py` with `workflow_mode="hearing_prep"`) | `hearing_brief_output` | `docx_path`, `risk_annotations` |

**New LexState fields:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `hearing_date` | `Optional[str]` | reminders, hearing_draft | hearing_intake |
| `hearing_issues` | `Optional[List[str]]` | hearing_draft | hearing_intake |
| `last_hearing_summary` | `Optional[str]` | hearing_draft | hearing_intake (from MEMORY.md) |
| `hearing_brief_output` | `Optional[str]` | review, docx | hearing_draft |
| `anticipated_objections` | `Optional[List[str]]` | hearing_draft | hearing_draft (LLM) |
| `workflow_mode` | `Optional[str]` | graph routing | intake |

**New tools:** `get_matter_timeline` — reads MEMORY.md and extracts structured event list.

**New config flags:** `LEX_HEARING_PREP_ENABLED` (bool, default True)

**CRG impact radius:** MEDIUM

- `graph.py` — new sub-graph or new routing branch
- `state.py` — 5 new fields
- New skill file: `lexagent/skills/hearing_prep.md`
- CRIT-03 fix is a hard prerequisite

**Dependencies:** CRIT-03 (matter memory injection), Phase 7 complete (graph patterns stabilized).

**Rollout priority:** P1 (Phase 9)

---

### B2. Witness Examination Question Generator

**One-line description:** Given a matter brief and witness name/role, generates examination-in-chief questions, cross-examination questions, and re-examination questions.

**Business value:** Drafting witness questions is time-intensive and requires knowledge of evidentiary rules. The Evidence Act structure (examination-in-chief → cross → re-examination) is deterministic.

**Engineering complexity:** M

**New LangGraph nodes:** Inline in `hearing_draft.py` as a conditional block when `workflow_mode="witness_prep"`.

**New LexState fields:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `witness_list` | `Optional[List[dict]]` | hearing_draft | hearing_intake |
| `examination_questions` | `Optional[dict]` | review, docx | hearing_draft |

**New config flags:** None.

**CRG impact radius:** LOW (new fields, inline in existing hearing_draft node).

**Dependencies:** B1 (hearing prep sub-graph).

**Rollout priority:** P2 (Phase 9)

---

### B3. Opposing Argument Anticipation

**One-line description:** After generating the lawyer's arguments, the LLM plays opposing counsel and generates likely objections and rebuttals to each argument.

**Business value:** Identifying weaknesses in your own argument before the opposing counsel does is the most valuable pre-hearing exercise. Currently requires senior partner review.

**Engineering complexity:** S (given hearing_draft node already exists)

**New LangGraph nodes:** None. Second LLM pass in `hearing_draft.py`.

**New LexState fields:** `anticipated_objections: Optional[List[str]]` (already listed in B1).

**Rollout priority:** P2 (Phase 9)

---

### B4. Last-Hearing-to-Next-Hearing Memory Bridge

**One-line description:** Reads MEMORY.md for the last hearing entry and injects it as context into the hearing brief (what happened, what was ordered, what must happen next).

**Business value:** A lawyer with 40 active matters cannot remember what happened at the last hearing in each. This bridges the memory gap automatically.

**Engineering complexity:** S (CRIT-03 fix is the real work; this is built on top of it)

**New LangGraph nodes:** None. Implemented in `hearing_intake.py`.

**New LexState fields:** `last_hearing_summary` (already in B1).

**Dependencies:** CRIT-03 fix (matter memory injection).

**Rollout priority:** P1 (Phase 9)

---

## C. Procedural Intelligence

---

### C1. Court-Specific Document Formatting

**One-line description:** The `docx_writer.py` applies court-specific formatting rules (font, margin, numbering style) based on `jurisdiction`.

**Business value:** Delhi HC requires Times New Roman 12pt with 1-inch margins and specific line spacing. SC uses different rules. A wrong format is a ground for return of documents.

**Engineering complexity:** M

Justification: `docx_writer.py` currently uses hardcoded formatting. Must be driven by a court-format YAML config file.

**New LangGraph nodes:** None.

**New LexState fields:** None (jurisdiction already in state).

**New tools:** None. `docx_writer.py` reads court format from `lexagent/data/court_formats/{court_code}.yaml`.

**New config flags:** `LEX_COURT_FORMAT_ENABLED` (bool, default True).

**CRG impact radius:** MEDIUM (docx_writer.py rewrite, tight coupling to state via `docx_writer.py` accepting full `LexState` is already a known issue — MED-coupling).

**Dependencies:** None. Can be built independently.

**Rollout priority:** P2 (Phase 9)

---

### C2. Interlocutory Application Sub-Graph (IA Sub-Graph)

**One-line description:** A dedicated sub-graph for drafting interlocutory applications (stay, injunction, discovery, contempt) with matter-type-specific intake and template.

**Business value:** IAs are the most frequently drafted documents in litigation practice. The current graph drafts them through the generic path. An IA-specific path captures urgency, grounds, and balance of convenience automatically.

**Engineering complexity:** L

Justification: New sub-graph (3 nodes), new skill file, new LexState fields, integration with main graph routing.

**New LangGraph nodes:**

| Node | File | Description |
|------|------|------------|
| `ia_intake` | `lexagent/nodes/ia_intake.py` | Captures IA type, grounds, urgency |
| `ia_draft` | `lexagent/nodes/ia_draft.py` | Drafts the application with standard grounds |

**New LexState fields:**

| Field | Type |
|-------|------|
| `ia_type` | `Optional[str]` — "stay", "injunction", "discovery", "contempt" |
| `ia_grounds` | `Optional[List[str]]` |
| `urgency_flag` | `Optional[bool]` |
| `balance_of_convenience` | `Optional[str]` |

**New skill file:** `lexagent/skills/interlocutory_application.md`

**CRG impact radius:** MEDIUM (graph.py routing, state.py, new skill)

**Dependencies:** Phase 7 complete (workflow_mode pattern established).

**Rollout priority:** P2 (Phase 9)

---

### C3. Document Classification Engine

**One-line description:** Intake node classifies the matter into a canonical document type (WP, CS, CRL, IA, SLP) and routes to the appropriate sub-graph.

**Business value:** Currently `matter_type` is free text and the skill loader does fuzzy keyword matching. Classification creates a first-class routing decision.

**Engineering complexity:** S

**New LangGraph nodes:** None. Extend intake node with a classification step before skill selection.

**New LexState fields:** `document_class: Optional[str]` — canonical enum: "WP", "CS_CIVIL", "CS_CRL", "IA", "SLP", "NOTICE", "CONTRACT", "OPINION".

**CRG impact radius:** LOW-MEDIUM (intake.py, graph.py routing, skills loader).

**Rollout priority:** P1 (Phase 8)

---

## D. Explainability + Contradiction Detection

---

### D1. Citation Chain Tracer

**One-line description:** Given a citation, traces the chain of cases that cited it, overruled it, or distinguished it, stored as a directed graph in SQLite.

**Business value:** A case may have been overruled 10 years after it was decided. Using an overruled case in court is grounds for serious professional embarrassment. This catches it.

**Engineering complexity:** L

Justification: Requires new SQLite schema (citation_graph table), new Kanoon fetching logic to extract "Cited in" references, new traversal algorithm.

**New LangGraph nodes:**

| Node | File | Inputs | Outputs |
|------|------|--------|---------|
| `citation_chain` | `lexagent/nodes/citation_chain.py` | `grounded_citations`, `research_findings` | `citation_chains`, `overruled_citations` |

This node can run in parallel with `review` via LangGraph `Send` API (see graph_expansion.md).

**New LexState fields:**

| Field | Type | Read by | Written by |
|-------|------|---------|-----------|
| `citation_chains` | `Optional[dict]` | review, docx | citation_chain node |
| `overruled_citations` | `Optional[List[str]]` | review (flags as HIGH risk) | citation_chain node |

**New tools:**

| Tool | File | Description |
|------|------|------------|
| `trace_citation_chain` | `lexagent/tools/citation_chain.py` | Recursively fetches citing cases from Kanoon |

**New SQLite table:** `citation_graph (citation TEXT, cites TEXT, relationship TEXT, fetched_at TEXT)` — added to `sessions.db` schema.

**New config flags:** `LEX_CITATION_CHAIN_ENABLED` (bool, default False — expensive, requires Kanoon calls per citation).

**CRG impact radius:** MEDIUM

- `cite.py` (chain tracer runs after grounded_citations are built)
- `review.py` (overruled_citations added to risk_annotations as HIGH)
- `sessions.db` schema (new table)
- `state.py` (2 new fields)

**Dependencies:** CRIT-01 fix (citation grounding must be reliable before chain traversal makes sense). Phase 7 Kanoon API backend (Playwright browser pool too slow for chain traversal).

**Rollout priority:** P1 (Phase 9)

---

### D2. Ratio Decidendi Extractor

**One-line description:** For each fetched judgment, uses the LLM to extract the binding holding (ratio) vs. non-binding dicta (obiter), tagging each in `research_findings`.

**Business value:** LLMs frequently cite obiter dicta as binding precedent. This is a known hallucination vector. Tagging ratio vs obiter before the draft node runs prevents this category of error.

**Engineering complexity:** M

**New LangGraph nodes:** None. Additional LLM pass in research node after fetching judgments.

**New LexState fields:** `research_findings` dict extended with `ratio: str` and `is_obiter: bool` per finding.

**New config flags:** `LEX_EXTRACT_RATIO` (bool, default False — adds one LLM call per judgment).

**CRG impact radius:** MEDIUM

- `research.py` (new post-fetch LLM pass)
- `draft.py` (must use `ratio` field in "Verified case law" instruction, not full text)
- `cite.py` (ratio text improves BM25 retrieval quality)

**Dependencies:** CRIT-02 fix (RAPTOR injection must be clean before adding more research_findings mutations).

**Rollout priority:** P2 (Phase 9)

---

### D3. Contradiction Detector

**One-line description:** Before the review node, an LLM checks whether any argument in the draft contradicts the holding of a cited case.

**Business value:** A lawyer citing a case in support of a proposition while the case actually holds the opposite is a catastrophic error. Happens when LLMs confuse majority and dissent opinions.

**Engineering complexity:** M

**New LangGraph nodes:**

| Node | File | Inputs | Outputs |
|------|------|--------|---------|
| `contradiction_check` | `lexagent/nodes/contradiction_check.py` | `draft_output`, `grounded_citations`, `research_findings` | `contradiction_flags` |

**New LexState fields:** `contradiction_flags: Optional[List[dict]]` — `[{citation, argument_text, contradiction_note}]`.

**New config flags:** `LEX_CONTRADICTION_CHECK` (bool, default False — one LLM call per verified citation).

**CRG impact radius:** MEDIUM

- `graph.py` (new node between `cite` and `review`)
- `state.py` (1 new field)
- `review.py` (reads contradiction_flags, adds to risk_annotations)

**Dependencies:** CRIT-01 fix (citation grounding must be reliable), D2 (ratio extractor makes contradictions detectable).

**Rollout priority:** P2 (Phase 9)

---

### D4. Confidence Scoring on Legal Propositions

**One-line description:** The draft node tags each major legal proposition with a confidence score (0–1) based on how well the supporting citations were grounded.

**Business value:** A lawyer needs to know which parts of a draft are solid and which are shaky. Currently risk_annotations only flag structural issues (word count, unverified citations). This adds proposition-level confidence.

**Engineering complexity:** S

**New LangGraph nodes:** None. Additional scoring pass in `cite.py`.

**New LexState fields:** `proposition_scores: Optional[List[dict]]` — `[{proposition_text, score, supporting_citations}]`.

**CRG impact radius:** LOW (cite.py extension, state.py, review.py display).

**Rollout priority:** P3 (Phase 10)

---

## E. Hierarchical / PageIndex-Style Retrieval

---

### E1. PageIndex Multi-Level Hierarchical Index

**One-line description:** Extends the chunker to produce a three-level index: document → section → paragraph → sentence. Retrieval assembles context by combining the paragraph match with its parent section and document metadata.

**Business value:** The current flat BM25+TF-IDF retriever loses section context (a paragraph about "injunction" may be from a section titled "Damages" in a case that actually ruled against injunction). Parent context assembly prevents this misattribution.

**Engineering complexity:** L

Justification: Requires redesigning `chunker.py` to produce a tree structure, redesigning `retriever.py`'s `from_findings()` to index multiple levels, and updating `cite.py` to request hierarchical context assembly.

**New LangGraph nodes:** None. Contained within retrieval layer.

**New LexState fields:** `retrieval_chunks` dict extended with `section_title` and `document_summary` fields per chunk (already partially present: `section_id` exists in `grounded_citations`).

**New tools:** None. Refactor of existing `chunker.py` and `retriever.py`.

**New config flags:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_HIERARCHICAL_INDEX` | `False` | Enables 3-level index; higher memory, better precision |
| `LEX_SECTION_CONTEXT_TOKENS` | `512` | Tokens from parent section to include with chunk |

**CRG impact radius:** HIGH

- `chunker.py` (Chunk dataclass extension)
- `retriever.py` (from_findings, retrieve methods)
- `cite.py` (calls retriever)
- `raptor_summarizer.py` (uses chunk_text from chunker)
- All tests for chunker and retriever

**Dependencies:** CRIT-01 fix (threshold bypass must be fixed before adding a more complex retrieval path that could introduce new threshold bypass paths).

**Rollout priority:** P1 (Phase 9)

---

### E2. Statute-to-Case Mapping Index

**One-line description:** Builds and persists a SQLite index mapping each statute section to all cases that interpreted it, updated on each research run.

**Business value:** When drafting an argument under IPC 420, the lawyer needs every SC case on that section — not just the top 3 from the current search. This index accumulates across all matters.

**Engineering complexity:** M

**New LangGraph nodes:** None. Research node writes to the index; a new tool queries it.

**New LexState fields:** None.

**New tools:**

| Tool | File | Description |
|------|------|------------|
| `query_statute_index` | `lexagent/tools/statute_index.py` | `search_by_statute(section: str) -> List[dict]` |

**New SQLite table:** `statute_case_index (statute TEXT, section TEXT, case_name TEXT, citation TEXT, relevance TEXT, fetched_at TEXT)` in `sessions.db`.

**New config flags:** `LEX_STATUTE_INDEX_ENABLED` (bool, default True).

**CRG impact radius:** MEDIUM

- `research.py` (writes to index after each Kanoon fetch)
- `sessions.db` (new table)
- New tool registration

**Rollout priority:** P2 (Phase 9)

---

### E3. Cross-Matter Precedent Cache

**One-line description:** When a citation has already been fetched and verified in a prior matter, retrieve it from a local cache instead of fetching from Kanoon again.

**Business value:** A lawyer doing 20 injunction matters per year will repeatedly fetch the same 15 landmark cases. This eliminates redundant Kanoon calls (rate limits, latency) and makes the agent faster over time.

**Engineering complexity:** S

**New LangGraph nodes:** None.

**New tools:** `check_precedent_cache` — SQLite lookup before Kanoon fetch in research node.

**New SQLite table:** `precedent_cache (citation TEXT PRIMARY KEY, full_text TEXT, fetched_at TEXT, case_name TEXT, court TEXT, decision_date TEXT)` in `sessions.db`.

**New config flags:** `LEX_PRECEDENT_CACHE_ENABLED` (bool, default True).

**CRG impact radius:** LOW (research.py modified to check cache before Kanoon call).

**Dependencies:** None. Can ship independently.

**Rollout priority:** P2 (Phase 9, reduces Kanoon load as citation chain traversal is added)

---

## F. Filing Compliance

---

### F1. Cause-Title Validator

**One-line description:** Validates that the cause title in the draft matches the required format for the specified court (case type abbreviation, year format, party name format).

**Business value:** A wrong cause title (e.g., "CS (OS)" vs "CS" vs "OMP") causes the registry to return the filing. This is a deterministic check that should never require LLM reasoning.

**Engineering complexity:** S

**New LangGraph nodes:** None. New check in `review.py`.

**New LexState fields:** `cause_title_issues: Optional[List[str]]`

**New config flags:** None.

**CRG impact radius:** LOW

**Rollout priority:** P2 (Phase 9)

---

### F2. Annexure Numbering Checker

**One-line description:** Scans the draft text for references to annexures (e.g., "Annexure A", "Exhibit 1") and verifies that all referenced annexures are declared and sequentially numbered.

**Business value:** Missing or mis-numbered annexures are a common defect that causes courts to return filings. This is a pure regex check.

**Engineering complexity:** S

**New LangGraph nodes:** None. New check in `review.py`.

**New LexState fields:** `annexure_issues: Optional[List[str]]`

**CRG impact radius:** LOW

**Rollout priority:** P2 (Phase 9)

---

### F3. E-Filing Format Validator

**One-line description:** Validates that a generated .docx meets e-filing requirements for the target court (SC SCIS, Delhi HC e-filing, eCourts).

**Business value:** E-filing rejections due to format issues (wrong paper size, wrong margin, bookmarking missing, PDF/A requirement) delay matters.

**Engineering complexity:** M

Justification: Different courts have different validation rules. Must maintain court-format YAML data files.

**New LangGraph nodes:** None. Post-review validation step, triggered when `docx_path` is set.

**New tools:** `validate_efiling_format` — reads `docx_path` and checks against court format rules.

**New config flags:** `LEX_EFILING_VALIDATE` (bool, default False)

**CRG impact radius:** LOW-MEDIUM (review.py, docx_writer.py, new tool)

**Dependencies:** C1 (court-specific formatting must be applied before validation).

**Rollout priority:** P3 (Phase 10)

---

## G. Matter Memory + Knowledge Graph

---

### G1. Matter Entity Graph (Persistent Knowledge Graph)

**One-line description:** Extends `legal_kg.py` to persist the entity graph across sessions per matter, making `save_entity_graph()` actually called (currently dead code).

**Business value:** `save_entity_graph()` in `legal_kg.py` is implemented but never called from the graph (impact_radius.md confirms this). The entity graph is built in state but thrown away. Persisting it enables cross-session entity lookup (parties, judges, cases) without re-fetching.

**Engineering complexity:** S

Justification: The infrastructure exists. This is wiring `research.py` to call `save_entity_graph()` after building it, and providing a `query_entity_graph()` tool.

**New LangGraph nodes:** None.

**New tools:** `query_entity_graph` — queries persisted `entity_graphs` table in sessions.db.

**New config flags:** None (uses existing `graphrag_enabled` flag).

**CRG impact radius:** LOW (research.py one-line addition, existing tool infrastructure).

**Dependencies:** `graphrag_enabled=True`. Fix is trivial — call `save_entity_graph()` in research node after building `entity_graph`.

**Rollout priority:** P0 (Phase 7 — trivial fix, high value, should land in pre-Phase 7 sprint)

---

### G2. Cross-Matter Client Intelligence

**One-line description:** When drafting for a client with prior matters, retrieves relevant prior matter summaries from MEMORY.md files and injects them as client context.

**Business value:** A lawyer representing the same client in a second matter needs to know what was resolved in the first. Currently CRIT-03 means even single-matter memory is broken. This is the multi-matter extension.

**Engineering complexity:** M (CRIT-03 fix is the prerequisite work)

**New LangGraph nodes:** None.

**New tools:** `query_client_history` — reads all MEMORY.md files for a `client_id`.

**New LexState fields:** `client_history_summary: Optional[str]`

**New config flags:** `LEX_CLIENT_MEMORY_ENABLED` (bool, default True)

**CRG impact radius:** MEDIUM (intake.py loads client history, draft.py injects it, memory subsystem).

**Dependencies:** CRIT-03 fix, client_id in LexState (not currently present — must be added).

**Rollout priority:** P1 (Phase 8)

---

## H. Enterprise Readiness

---

### H1. Multi-Lawyer Workspace

**One-line description:** Adds a `workspace_id` field to scope all data (matters, sessions, SOUL.md) to a firm or lawyer, enabling shared matters with role-based access.

**Business value:** A law firm with 5 lawyers needs to share matters (senior assigns research to junior). Currently there is no concept of multi-user ownership.

**Engineering complexity:** XL

Justification: Requires auth model, data isolation, role-based routing in CLI and Telegram gateway, schema migration.

**New LangGraph nodes:** None (access control is not in the graph layer).

**New LexState fields:** `workspace_id: Optional[str]`, `user_role: Optional[str]` ("senior", "junior", "paralegal")

**New config flags:** `LEX_WORKSPACE_ID`, `LEX_USER_ROLE`

**CRG impact radius:** HIGH

- All memory read/write calls must scope to `workspace_id`
- `session_store.py` schema migration required
- `cli.py` must pass `workspace_id` to every operation
- `gateway/telegram.py` must map Telegram user_id to workspace + role

**Dependencies:** Phase 8 complete (stable single-user baseline), MED-09 fix (WAL mode for concurrent SQLite writes).

**Rollout priority:** P2 (Phase 10)

---

### H2. Audit Trail

**One-line description:** Every LLM call is logged to a SQLite table with: timestamp, node, model, input token count, output token count, input hash, output hash, matter_id.

**Business value:** Professional liability requires lawyers to show what the AI generated and when. An audit log also enables cost tracking per matter.

**Engineering complexity:** M

**New LangGraph nodes:** None. Middleware pattern: wrap `get_llm()` calls with an audit logger.

**New SQLite table:** `llm_audit (id INTEGER PRIMARY KEY, timestamp TEXT, matter_id TEXT, node TEXT, model TEXT, input_tokens INTEGER, output_tokens INTEGER, input_hash TEXT, output_hash TEXT, latency_ms INTEGER)`

**New config flags:** `LEX_AUDIT_ENABLED` (bool, default True)

**CRG impact radius:** MEDIUM (_llm.py refactored to log; sessions.db schema change)

**Dependencies:** None.

**Rollout priority:** P1 (Phase 10)

---

### H3. PII Detection Pipeline

**One-line description:** Before the draft node runs, a PII detection pass scans `research_findings` and user input for Aadhaar numbers, PAN numbers, phone numbers, and addresses, replacing them with `[REDACTED:<type>]`.

**Business value:** Sending client Aadhaar numbers to Anthropic's API is a data protection risk. Indian IT Act and emerging data protection rules (DPDPA 2023) impose obligations on data processors.

**Engineering complexity:** M

Justification: Regex covers most Indian PII patterns. DPDPA-specific categories require some legal judgment about what counts as personal data in legal documents (party names are arguably not PII in a public court context).

**New LangGraph nodes:**

| Node | File | Inputs | Outputs |
|------|------|--------|---------|
| `pii_redact` | `lexagent/nodes/pii_redact.py` | `research_findings`, `user_input` | `research_findings` (redacted), `pii_redaction_log` |

Run before `draft` node. Fixed edge: `research → pii_redact → draft`.

**New LexState fields:** `pii_redaction_log: Optional[List[dict]]` — what was redacted, for lawyer review.

**New config flags:** `LEX_PII_REDACT` (bool, default True), `LEX_PII_SHOW_LOG` (bool, default True)

**CRG impact radius:** MEDIUM

- `graph.py` (new node in sequence)
- `state.py` (1 new field)
- All research output passes through this node

**Dependencies:** None. Can be introduced at any phase.

**Rollout priority:** P1 (Phase 10)

---

### H4. Output Versioning

**One-line description:** Each draft run for a matter is stored as a versioned snapshot in `matter_memory.py`, and `lex draft --matter-id M001` shows a diff from the previous version.

**Business value:** Lawyers iterate drafts over multiple sessions. Without versioning, prior versions are overwritten and the change history is lost.

**Engineering complexity:** S

**New LangGraph nodes:** None. Extension of `matter_memory.save_matter_memory()`.

**New LexState fields:** `draft_version: Optional[int]`

**New config flags:** `LEX_VERSION_DRAFTS` (bool, default True)

**CRG impact radius:** LOW (matter_memory.py, cli.py output display)

**Dependencies:** CRIT-03 fix (memory infrastructure must be reliable first).

**Rollout priority:** P2 (Phase 10)

---

### H5. Cost Tracking Per Matter

**One-line description:** The audit trail (H2) feeds a cost aggregation query that computes total LLM API spend per matter using a configurable price table.

**Business value:** Law firms need to recover AI costs from clients. "This matter used 150K tokens at ₹0.80/1K = ₹120" is a billing line item.

**Engineering complexity:** S (depends on H2 audit trail)

**New LangGraph nodes:** None.

**New config flags:** `LEX_COST_TRACKING_ENABLED` (bool, default True), `LEX_TOKEN_PRICE_TABLE` (path to YAML price file)

**CRG impact radius:** LOW (reporting layer on top of audit trail)

**Dependencies:** H2 (audit trail).

**Rollout priority:** P2 (Phase 10)

---

### H6. White-Label Configuration

**One-line description:** The `.docx` output uses the law firm's name, address, and letterhead template from `SOUL.md` fields, replacing the current hardcoded "LexAgent" metadata footer.

**Business value:** Documents submitted to court must be on firm letterhead. The current `docx_writer.py` footer says "Generated by LexAgent" — cannot be filed as-is.

**Engineering complexity:** S

**New LangGraph nodes:** None.

**New LexState fields:** None (firm name/address from `lawyer_soul` dict).

**New config flags:** `LEX_FIRM_LETTERHEAD` (path to letterhead template .docx, optional)

**CRG impact radius:** LOW (docx_writer.py only)

**Dependencies:** SOUL.md must have firm fields populated.

**Rollout priority:** P2 (Phase 10)
