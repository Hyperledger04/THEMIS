# Gap Analysis

**Method:** CRG community/flow/hub analysis + direct module inspection + V3 roadmap comparison

---

## PRODUCT GAPS

---

### P1: No path from "upload documents" to "workspace populated"

**Problem:** A lawyer cannot today upload 10 PDFs and get back a structured matter workspace. The ingestion pipeline (`documents.py`, `extractors.py`, `chronology.py`) exists and is correct. The `handle_process_uploaded_documents` job handler exists and is correct. But there is no API endpoint or CLI command that enqueues a job. The RuntimeWorker polls a queue that nothing writes to.

**Evidence:** `runtime/jobs.py` has the handler. `runtime/worker.py` has the poll loop. `gateway/control_plane.py` has no `/jobs/enqueue` or `/documents/upload` endpoint. `cli.py` has no `lex ingest` command.

**Impact:** The entire living-agent value proposition — "upload documents and wake up to a structured matter" — is blocked at the enqueue step. This is a wire-up gap, not a capability gap.

**Confidence:** Very high.

---

### P2: Learning loop is write-only

**Problem:** `FeedbackService`, `StylePreferenceService`, and `PlaybookNoteService` store feedback correctly. Nothing reads them at draft time. Lawyer edits are captured but never injected into future prompts. The system cannot improve.

**Evidence:** `learning/feedback.py`, `preferences.py`, `playbooks.py` exist. Search for `StylePreferenceService` or `FeedbackService` imports in `nodes/draft.py` or `nodes/react_research.py` — no hits. Learning is orphaned from the drafting pipeline.

**Impact:** High strategic — this is the compounding moat that differentiates LexAgent from a generic AI wrapper. Without the read side, every draft is equally good (or bad) as the first one.

**Confidence:** Very high.

---

### P3: Post-draft approval workflow is partial

**Problem:** `AgentApproval` model exists. Worker enforces `requires_approval` check. But there is no UI surface for lawyers to approve/reject agent actions — only `pending_action` in LexState for post-draft Telegram menu. For background jobs (overnight research, risk analysis), there is no approval notification delivery path.

**Evidence:** `runtime/models.py::AgentApproval` is well-designed. `worker.py` checks `requires_approval`. No endpoint in `control_plane.py` handles `POST /approvals/{id}/approve`. `AgentNotification` model exists but `notification_agent` handler is not implemented.

**Impact:** Blocks the living agent from doing any external or mutating action safely. Exactly the right constraint — just needs the approval delivery path.

**Confidence:** High.

---

### P4: Workspace models not connected to graph execution

**Problem:** Graph nodes produce `draft_output`, `research_findings`, `unverified_citations` as raw dict fields in `LexState`. None of these are written to the typed workspace tables (`drafts`, `authorities`, `research_memos`). The workspace is a parallel truth that is never updated by the graph.

**Evidence:** `workspace/repository.py` has `save_draft()`, `save_authority()`, `save_research_memo()`. None of these are called from any `nodes/*.py` file.

**Impact:** Every run produces work that is invisible to the workspace and therefore invisible to the living agent, the terminal IDE, and future retrieval. The most important data in the system is stored in the wrong place.

**Confidence:** Very high.

---

## ARCHITECTURE GAPS

---

### A1: LexState is a 57-field TypedDict anti-pattern

**Problem:** `state.py` mixes matter facts (parties, jurisdiction), workflow flags (intake_complete, citations_verified), gateway identity (telegram_user_id, voice_session_id, firm_id), output artifacts (draft_output, docx_path), and RAG intermediates (retrieval_chunks, raptor_tree) in a single flat dict.

**Evidence:** `state.py` lines 1–131. Every new feature adds 2-5 fields. The V3 roadmap explicitly identifies this: "too loose for a legal OS."

**Impact:** `LexState` will break at ~80 fields. Adding new workflows requires new fields + new routing logic. Testing requires mocking entire state dicts. V3's planner cannot generate DAGs when the state schema is monolithic.

**Confidence:** Very high.

---

### A2: No event bus — runtime events are fire-and-forget

**Problem:** `RuntimeEvent` model exists. No event dispatcher, subscriber registry, or event-driven reactions are implemented. The living agent's document processing completes, creates workspace objects, and then stops. Nothing is notified; no downstream job is triggered.

**Evidence:** `runtime/models.py::RuntimeEvent`. No `event_bus.py` in `runtime/`. No `events.py`. Worker calls `repo.update_job_status("completed")` then stops — does not publish a `DOCUMENT_PROCESSED` event.

**Impact:** V3 requires event-driven reactions: `DOCUMENT_PROCESSED` → `extract_facts` → `FACTS_EXTRACTED` → `build_chronology` → etc. Without an event bus, each pipeline step must be manually chained as job dependencies. This is operationally fragile.

**Confidence:** High.

---

### A3: No planner — all routing is static conditional edges

**Problem:** LangGraph graph has 7 hardcoded nodes. Routing is determined by `workflow_mode` and `matter_type` checks in closure functions. Adding a new document type (NI Act Section 138, arbitration) requires adding graph nodes + routing conditions + state fields.

**Evidence:** `graph.py::build_graph()` — 7 add_node calls, 6 add_edge/add_conditional_edges calls. `_NO_RESEARCH_TYPES` is a hardcoded tuple. No planner.py in `runtime/`.

**Impact:** The system cannot adapt its execution to matter complexity, evidence availability, or jurisdiction. A writ petition and a vakalatnama require different steps; the graph cannot know this without a planner.

**Confidence:** Very high.

---

### A4: Security wiring gaps

**Problem:** `security/` package is complete and correct. The control plane and session store do not consistently apply it. `_verify_token()` in `control_plane.py` exists but it is not clear all routes enforce it. SQLite session queries do not include `firm_id` predicates.

**Evidence:** `gateway/control_plane.py` — 489 lines, `_verify_token` function exists. CRG `security-key` community has 31 nodes with cohesion 0.1493 — moderate coupling suggests external dependencies rather than tight internal cohesion. `test_matter_isolation.py` tests Postgres workspace isolation but not session isolation.

**Impact:** In single-user personal mode, negligible. In multi-tenant mode, a missing `firm_id` predicate is a confidentiality bleed (§11A Failure Mode 3).

**Confidence:** High.

---

### A5: Research node is retrieval, not investigation

**Problem:** `react_research.py` calls tools and accumulates findings. It does not form hypotheses, search for adverse authorities, compare conflicting judgments, or produce a structured research conclusion with confidence levels.

**Evidence:** `react_research.py::run` has 50 out-degree (calls many things). CRG flow `run` has 18 nodes. No `hypothesis`, `adverse_search`, `comparison`, or `conclusion_confidence` fields in `LexState`.

**Impact:** The system can find cases that mention relevant terms. It cannot determine whether those cases are distinguishable, overruled, or binding in the specific jurisdiction. This is the difference between a keyword search tool and a research memo.

**Confidence:** High.

---

### A6: Citation verification does not check ratio decidendi

**Problem:** `cite.py` extracts citations from draft text and verifies them against the research corpus. Verification is "does this case exist in our corpus?" not "does the paragraph cited actually say what the draft claims?"

**Evidence:** `workspace/models.py::Authority` has `verified_excerpt`, `paragraph_number`, `verification_status` (tri-state). These fields are never populated by `cite.py`. `cite.py::_verify_citations()` exists (lines 54–70) but the CRG shows it only calls within `cite.py`.

**Impact:** §11A Failure Mode 1 (Citation Drift) — the most dangerous practitioner failure mode. The case exists, the URL resolves, but the proposition is wrong. This is structurally undetectable by the current cite node.

**Confidence:** Very high.

---

## AGENT SYSTEM GAPS

---

### AS1: Chamber agents do not exist

**Problem:** V3 roadmap specifies 10 specialist agents (Senior Counsel, Planner, Research, Statutory, Procedure, Evidence, Drafting, Citation, Risk, Client). `agents/faces.py` contains persona *descriptions* — not functional agents with isolated state, tool access, or LangGraph subgraphs.

**Evidence:** `agents/faces.py` (117 lines) — character descriptions. `agents/registry.py` (155 lines) — `AgentRegistry` lookup. No `chamber/` directory. No `senior.py`, `research.py`, `drafting.py` in `agents/`.

**Impact:** Without chamber agents, multi-pass legal review (draft → adversarial critique → revision) cannot exist. The system produces a single draft with no internal quality challenge.

**Confidence:** Very high.

---

### AS2: Agent responsibilities are ambiguous in the graph

**Problem:** The single LangGraph graph acts as all agents simultaneously — it intakes, researches, drafts, cites, and reviews. There is no separation of concerns. The "ReAct research node" is a different code path from the "legacy research node" (research.py) but both exist and the graph switches between them implicitly.

**Evidence:** `graph.py` registers `"research": react_research.run` — the legacy `research.py::run` (419 lines) is imported but not used in the active graph. This dead code creates confusion: which research path is canonical?

**Impact:** Onboarding confusion. Accidental reversion to legacy path. Test coverage split across two paths.

**Confidence:** High.

---

## LEGAL CAPABILITY GAPS

---

### LC1: No court hierarchy enforcement in retrieval

**Problem:** Qdrant KB uses a single collection model. Indian Kanoon results, Tavily web results, and firm documents are potentially mixed in the same vector space. No corpus namespace separation exists in the retrieval pipeline.

**Evidence:** `kb/collections.py` — single collection logic. No `corpus_namespace` parameter in `retriever.py` or `kb_query.py`. `LexConfig` has `qdrant_enabled=False` by default.

**Impact:** §11A Failure Mode 2 (Jurisdictional Conflation). A Privy Council decision and a Supreme Court of India binding precedent can appear with equal retrieval weight. The draft does not know the difference.

**Confidence:** High.

---

### LC2: No chronology in the drafting prompt

**Problem:** The V3 roadmap (§11A, Insight 3) explicitly requires: "Before the drafting node runs, Evidence Counsel and Procedure Counsel must inject the matter chronology, prior court orders, filed documents, and limitation events." The draft node today receives: soul, skill, research_findings, retrieval_chunks. No chronology injection.

**Evidence:** `nodes/draft.py` — check prompt construction. No chronology, no prior orders, no evidence timeline in the drafting context.

**Impact:** Drafts are grounded in general case law, not in the specific procedural history of the matter. A writ petition that ignores the prior High Court order in the same matter is legally invalid.

**Confidence:** High.

---

### LC3: No audit trail for agent-generated legal facts

**Problem:** When the living agent extracts a fact from a document, it is stored in the `extracted_facts` table with `status="extracted"` and `confidence`. There is no mechanism for a lawyer to confirm, dispute, or correct this fact — and no record of whether it was confirmed before being used in a draft.

**Evidence:** `workspace/models.py::ExtractedFact` has `status` field with `["extracted", "confirmed", "disputed", "needs_source"]`. No endpoint or CLI to transition from `extracted` to `confirmed`. No node checks `status` before using a fact.

**Impact:** Unconfirmed agent-extracted facts may reach drafts as if confirmed. In legal work, this conflation between alleged and proved is professionally dangerous.

**Confidence:** High.

---

## DX GAPS

---

### DX1: Tests are structural bridges (anti-pattern)

**Problem:** CRG bridge analysis shows that 13 of 15 bridge nodes (highest betweenness centrality) are test functions. This means the test suite is over-coupled to specific implementation details. Refactoring any production function breaks tests in ways that do not reflect actual correctness regressions.

**Evidence:** CRG bridge_nodes: `test_voice_websocket_text_message`, `test_creates_alert_when_deadline_due_soon`, `test_run_citation_gate_drops_bad_findings`, `test_run_produces_draft_output_on_success`, etc. as top bridges. `LexConfig` is the only production bridge.

**Impact:** High refactoring cost. Moving from `LexState` dict to workspace IDs will require rewriting most of the 669 tests. Tests assert implementation details (specific dict keys), not behavior contracts.

**Confidence:** High.

---

### DX2: `run_setup_wizard` is a god function (113 out-degree)

**Problem:** `memory/soul.py::run_setup_wizard` calls 113 different things — the highest out-degree in the codebase. This function is responsible for the entire first-run experience but has become a single-function integration layer.

**Evidence:** CRG hub_nodes: `run_setup_wizard` out_degree=113, total_degree=114. This is not a test — it is a production function that every CLI user hits on first run.

**Impact:** Untestable in isolation. Any change to any of its 113 callees can break the wizard. A new user's first experience is gated on this function.

**Confidence:** Very high.

---

### DX3: Dual-purpose codebase (teaching + product) creates opposing forces

**Problem:** `CLAUDE.md` states "Teaching build. Optimise for clarity over cleverness." The same codebase also contains enterprise security, multi-tenant isolation, and a 16-phase production roadmap. Teaching code requires verbose comments; production code should be maintainable. They conflict.

**Evidence:** `CLAUDE.md` §Code Rules: "Add `# LANGGRAPH:` comment the first time any LangGraph pattern appears." `course/` directory with 11 phases. `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` with 16 production phases.

**Impact:** Unclear which files are pedagogical examples (delete-safe) vs production code (modify-carefully). New contributors cannot tell which standards apply where.

**Confidence:** High.
