# Opportunities

**Filter:** Features that strengthen V3, leverage existing architecture, improve moat, avoid generic chatbot behavior.

---

## O1 — Wire the enqueue path: `lex ingest <file>` → job → worker → workspace

**Idea:** Add a single CLI command `lex ingest <pdf|dir>` and a `POST /matters/{id}/documents` control plane endpoint that creates a document record and enqueues a `process_uploaded_documents` job. The worker, ingestion pipeline, and workspace repository are already correct — they just need to be wired to an entry point.

**Why:** This is the highest-leverage single wire-up in the codebase. `RuntimeWorker`, `ingest_file()`, `extract_from_pages()`, `build_chronology()`, and `PostgresWorkspaceRepository` all exist and work. The only missing piece is the creation of a job record. This unlocks the living-agent value proposition in one session of work.

**Difficulty:** Low — add ~50 lines: a `repo.enqueue_job()` call from CLI + control plane endpoint.

**Strategic value:** Transforms LexAgent from "draft on demand" to "process matter file continuously." This is the product wedge.

**Architecture fit:** Perfect — uses `runtime/worker.py`, `runtime/jobs.py`, `ingestion/documents.py`, `workspace/repository.py` exactly as designed. No new abstractions needed.

**Tag:** FOUNDATIONAL / QUICK WIN

---

## O2 — Close the learning loop: inject preferences into draft prompt

**Idea:** At draft time, call `StylePreferenceService.get_preferences(user_id, matter_type, doc_type)` and inject returned preferences as a few-shot section in the drafting prompt. After draft delivery, offer a "Save this style" button in Telegram or CLI.

**Why:** `StylePreference` model, `StylePreferenceService`, and `FeedbackItem` are all implemented. The drafting prompt is assembled in `nodes/draft.py`. The gap is one function call at prompt assembly time, and one feedback capture at output time. With this closed, the system begins compounding — each accepted draft makes the next one better.

**Difficulty:** Low — add `StylePreferenceService` import to `draft.py`, fetch preferences, append to prompt. Add a "save preference" callback in Telegram handler.

**Strategic value:** This is the compounding moat. After 10 accepted drafts for a given lawyer, the output quality should be measurably different from a fresh install. This is what Harvey cannot offer a solo practitioner.

**Architecture fit:** Strong — all supporting infrastructure exists.

**Tag:** FOUNDATIONAL / MOAT

---

## O3 — Graph nodes write to workspace at run completion

**Idea:** At the end of `review.run()` (the terminal node), save `Draft`, `Authority` records, and `ResearchMemo` to the `PostgresWorkspaceRepository`. Pass the `postgres_url` via `LexConfig`. This makes every graph run a workspace-persisting event.

**Why:** Currently, every run produces output that lives only in `LexState` checkpointer state and markdown files. The workspace repository (`save_draft`, `save_authority`, `save_research_memo`) is correct and tested. The terminal node (`review.py`) is the natural write point — it already has the complete picture.

**Difficulty:** Medium — `review.py::run()` must instantiate a repository, create typed objects from `LexState` fields, and persist them. Requires `postgres_url` to be set. Must handle the MemorySaver (no Postgres) case gracefully.

**Strategic value:** Once workspace is populated from graph runs, the terminal and living agent can read from a single source of truth. Morning briefs, research memos, and risk analyses can be generated from actual prior work.

**Architecture fit:** Strong — workspace models and repository are designed exactly for this.

**Tag:** FOUNDATIONAL

---

## O4 — Ratio verification: extract the actual paragraph, not just the case

**Idea:** In `cite.py::_verify_citations()`, after confirming the case exists, fetch the specific paragraph(s) that contain the cited proposition. Compare the drafted claim against the extracted excerpt using an LLM judge. Set `Authority.verification_status` to `verified` / `partial` / `contradicted` accordingly.

**Why:** §11A Failure Mode 1 (Citation Drift) is the most dangerous practitioner failure mode. The workspace `Authority` model already has `verified_excerpt`, `paragraph_number`, `verification_status` tri-state, and `proposition` fields — the data model is designed for exactly this. The verification logic in `cite.py` only checks case existence. Closing this gap is a trust-building feature that practitioners will immediately notice.

**Difficulty:** Medium-High — requires: (1) Kanoon API call to fetch full judgment text, (2) paragraph extraction via regex or LLM, (3) LLM comparison of proposition vs. excerpt.

**Strategic value:** Extremely high. No other Indian legal AI tool performs ratio verification at the paragraph level. This becomes a marketing claim: "Our citations are verified at the ratio level, not just the case level."

**Architecture fit:** Strong — `Authority` model is ready. Kanoon API client exists. `cite.py` is the right place.

**Tag:** MOAT

---

## O5 — Morning brief job handler

**Idea:** Implement `handle_morning_brief` as a RuntimeWorker job handler. It queries the workspace for: (a) active matters, (b) upcoming deadlines in the next 14 days, (c) new unreviewed workspace objects (facts, authorities, drafts), (d) open tasks. It produces a structured brief as an `AgentArtifact`, then sends via `AgentNotification` to `preferred_gateway`.

**Why:** This is the flagship living-agent behavior — the lawyer wakes up to a prepared briefing. All supporting infrastructure exists: workspace queries, `AgentArtifact`, `AgentNotification`, notification channel dispatch. The handler itself is a ~150-line LLM call over structured workspace data.

**Difficulty:** Medium — implement handler, add cron scheduling via APScheduler, wire notification dispatch.

**Strategic value:** High — this is the single feature most likely to generate "how did I ever work without this?" moments. It makes the system feel alive rather than reactive.

**Architecture fit:** Strong — uses RuntimeWorker, workspace repository, notification models exactly as designed.

**Tag:** FOUNDATIONAL / QUICK WIN

---

## O6 — Corpus namespace partitioning in Qdrant

**Idea:** When indexing documents into Qdrant, tag each chunk with a `corpus_namespace` payload field (`corpus:india_sc`, `corpus:india_hc:delhi`, `corpus:statutes`, `corpus:firm_docs`, etc.). Modify `retriever.py` to accept a `namespaces` filter parameter. Pass tier-weighted namespace lists from `react_research.py` based on the matter's jurisdiction.

**Why:** §11A Failure Mode 2 (Jurisdictional Conflation). The workspace `Authority` model already carries `corpus_namespace`. The retriever currently does flat cosine search across mixed corpus content. This is a retrieval architecture requirement, not a prompt instruction — prompting alone cannot fix it because the model cannot know what it was not shown.

**Difficulty:** Medium — Qdrant payload filters are well-supported. The change is in `kb/collections.py` (add namespace tag on upsert) and `tools/retriever.py` (add filter param).

**Strategic value:** High — this prevents the category of practitioner embarrassment that ends client relationships (citing foreign authority as binding Indian law).

**Architecture fit:** Strong — workspace models are ready.

**Tag:** FOUNDATIONAL / MOAT

---

## O7 — Approval delivery via Telegram inline button

**Idea:** When a living-agent job sets `requires_approval=True`, the notification handler sends a Telegram message with inline buttons: `✓ Approve` / `✗ Reject` / `👁 Review`. The callback handler calls `repo.approve_job()` / `repo.reject_job()`. This closes the human-in-the-loop approval gate for background agent actions.

**Why:** The approval model (`AgentApproval`) is designed. The worker checks `requires_approval`. The only gap is: the lawyer never receives notification, and there is no button to press. Without this, the living agent is permanently blocked from any action marked `requires_approval=True`.

**Difficulty:** Low-Medium — Telegram callback handler already handles inline buttons. Extend to handle approval_id callbacks.

**Strategic value:** Medium — necessary for correctness; not a moat feature on its own. Enables safe living-agent autonomy.

**Architecture fit:** Strong — `AgentApproval`, Telegram callbacks, worker all aligned.

**Tag:** FOUNDATIONAL

---

## O8 — Structured research memo as first-class output

**Idea:** After `react_research.py` completes, produce a `ResearchMemo` object (already defined in workspace models) with: query, authorities found (typed `Authority` objects), confidence levels, gaps identified, and next-search suggestions. Save to workspace. Deliver as a formatted document to the lawyer before the draft node runs.

**Why:** Currently, research findings are a `List[dict]` in `LexState` — unstructured, ephemeral, invisible to future sessions. If a lawyer asks the same research question next week, the system re-does the work. A stored `ResearchMemo` is retrievable, improveable, and citable in the draft.

**Difficulty:** Medium — `ResearchMemo` model exists. Change `react_research.py` to produce typed `Authority` objects and save a memo via workspace repository.

**Strategic value:** High — makes research a durable asset, not a throwaway graph intermediate.

**Architecture fit:** Strong — models ready, workspace ready.

**Tag:** FOUNDATIONAL

---

## O9 — Skill manifests with `workflow_dag` field

**Idea:** Upgrade skill `.md` files to `.yaml` manifests with a `workflow_dag` field that specifies the node sequence for that matter type: `[intake, research, evidence_timeline, draft, cite_strict, risk_attack, revision, review]`. The graph can then read the manifest at runtime and execute the declared sequence rather than the hardcoded static graph.

**Why:** This is V3 Phase 7 (Dynamic Planner) at minimal cost. Instead of a full LLM planner, use human-curated skill manifests as deterministic DAG specifications. Legal procedure is well-defined — a writ petition always needs maintainability analysis before drafting. This knowledge should be in a skill file, not in the LLM's context window.

**Difficulty:** High — requires graph execution model change. But the skill loader, manifest structure, and config are ready. Start with template DAGs, not LLM-generated ones.

**Strategic value:** Very high — this is what makes LexAgent adaptable to new matter types without code changes.

**Architecture fit:** Good — skills loader exists. Requires graph.py refactor.

**Tag:** MOAT

---

## O10 — Chronology injection into draft prompt

**Idea:** Before `draft.run()` executes, query `workspace.get_chronology_items(matter_id)` and inject them as a structured section in the drafting prompt. Add a `prior_orders: Optional[List[str]]` field to LexState or pass directly from workspace.

**Why:** §11A Insight 3 — "A court-ready pleading is grounded in the procedural history of the specific matter... as much as in case law." Currently, drafts are grounded only in general research findings. They do not know what has already been filed, what orders have been issued, or what the procedural posture is.

**Difficulty:** Low — add a workspace query in `draft.py`, format chronology as structured context, inject into prompt.

**Strategic value:** High — makes the difference between a generic template and a matter-specific legal document. This is what lawyers are paying for.

**Architecture fit:** Strong — `ChronologyItem` model and workspace repository ready.

**Tag:** QUICK WIN / MOAT
