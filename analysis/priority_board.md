# Priority Board

**Recommendation method:** Impact × Architecture fit × V3 alignment, filtered by effort and risk.

---

## Evaluation Table

| Idea | Impact | Effort | Risk | V3 Alignment |
|------|--------|--------|------|--------------|
| O1: Wire enqueue path (ingest → job → worker → workspace) | Very High | Very Low | Low | Phase 3 (Living Agent MVP) |
| O2: Close learning loop (inject preferences at draft time) | High | Low | Low | Phase 6 (Learning Loop) |
| O3: Graph nodes write to workspace at run end | Very High | Medium | Medium | Phase 2 (Canonical Workspace) |
| O4: Ratio verification (paragraph-level citation check) | Very High | Medium-High | Medium | Phase 5 (Verification) |
| O5: Morning brief job handler | High | Medium | Low | Phase 3 (Living Agent) |
| O6: Corpus namespace partitioning (Qdrant) | High | Medium | Low | Phase 9 (Legal Knowledge) |
| O7: Approval delivery via Telegram inline button | Medium | Low | Low | Phase 3 (Approval gates) |
| O8: Structured research memo as workspace object | High | Medium | Low | Phase 5 (Research Memos) |
| O9: Skill manifests with workflow_dag | High | High | High | Phase 7 (Dynamic Planner) |
| O10: Chronology injection into draft prompt | Very High | Low | Low | Phase 4 (Document Intelligence) |

---

## Top 5 Recommendations

---

### #1 — Wire the enqueue path

**What:** Add `lex ingest <file>` CLI command + `POST /matters/{id}/documents` endpoint. These create a `DocumentRecord` in the workspace and call `repo.enqueue_job("process_uploaded_documents", ...)`. The worker, ingestion pipeline, and workspace are already correct.

**Why this first:** It is a 1–2 day task that unlocks the entire living-agent value proposition. Every other V3 feature becomes more compelling once the workspace is being populated automatically. This is the keystone that makes V3 feel like an OS rather than a chatbot.

**What to watch:** The worker needs a running Postgres instance. Add a clear error message when `postgres_url` is not set.

---

### #2 — Workspace write in terminal node (`review.py`)

**What:** At the end of `review.run()`, if `postgres_url` is set, instantiate `PostgresWorkspaceRepository` and save: `Draft` (content, version, status), `Authority` records from `research_findings` (with corpus_namespace and court_tier from LexState jurisdiction), `ResearchMemo` (from research_findings summary). Handle the no-Postgres case silently.

**Why second:** This closes the fundamental architectural gap between the graph and the workspace. Once drafts and authorities live in the workspace, the morning brief, risk analysis, and learning loop all have access to real prior work. Everything downstream in V3 depends on this.

**What to watch:** Do not require Postgres for personal-mode CLI users. The no-Postgres fallback must remain seamless. Write to workspace *in addition to* `LexState` — do not remove existing `LexState` write paths until the workspace is stable.

---

### #3 — Chronology injection into draft prompt

**What:** In `draft.run()`, after building the system prompt, call `workspace.get_chronology_items(matter_id)` (if `matter_id` and `postgres_url` are set) and inject a structured "Matter Timeline" section into the prompt. Include prior court orders, filed document dates, limitation events.

**Why third:** This is a low-effort, high-trust change. A lawyer who sees their own matter chronology reflected in the draft — "Given the Bombay High Court's interim order dated 15 March 2024..." — immediately trusts the system more. This is the difference between a generic legal template and a matter-specific pleading.

**What to watch:** The workspace must have chronology items (requires O1 to have run). In the no-workspace case, fall through silently. Do not add a fake chronology from `LexState` dict fields.

---

### #4 — Close the learning loop read side

**What:** In `draft.run()`, call `StylePreferenceService.get_active_preferences(user_id, matter_type, doc_type)`. If preferences exist, prepend them as a few-shot section in the drafting system prompt: "This lawyer prefers: [pref 1], [pref 2]...". After draft delivery, add a "Save this style" action to the Telegram post-draft menu and the CLI.

**Why fourth:** The write side (capturing feedback) is implemented. The read side (injecting it) is missing. Closing this loop costs ~30 lines in `draft.py` + ~20 lines in feedback capture. The return on investment compounds: by draft 10, the output should be measurably different from draft 1. This is the feature that creates lawyer retention.

**What to watch:** Limit preference injection to 5-10 items per prompt to avoid context bloat. Do not inject preferences from a different firm's users (firm_id isolation).

---

### #5 — Ratio verification in citation node

**What:** In `cite.py::_verify_citations()`, for each verified citation: (a) fetch the full judgment from Kanoon API, (b) extract the paragraph(s) most semantically similar to the drafted proposition, (c) LLM-judge: does this paragraph support the proposition? Set `Authority.verification_status` to `verified` / `partial` / `contradicted`. Block final output on `contradicted`.

**Why fifth:** §11A Failure Mode 1 (Citation Drift) is the practitioner-critical failure mode that ends client trust before the product gains traction. The workspace `Authority` model already has all required fields. The Kanoon API client exists. This is a trust-building feature with no equivalent in any competing Indian legal AI tool.

**What to watch:** Adds one Kanoon API call per citation — cost and latency impact. Rate-limit the verification loop. Consider making ratio verification opt-in (`LEX_RATIO_VERIFY=true`) until performance is validated. Kanoon API must be in `api` mode (not `stub`) for this to work.

---

## What NOT to pursue next

**Chamber agents** — Premature. The planner does not exist. The workspace is not yet populated from graph runs. Specialist subagents need structured inputs (workspace objects) to be useful. Building chambers before the workspace/graph connection lands means building a racing car before building the road.

**Beast Terminal IDE** — Premature. The terminal should be a read/write client over runtime events and workspace objects. Neither is reliably populated yet. Building the terminal now means building a shell over empty tables.

**LexMemory OS (7-layer)** — Premature. The current file-based memory is adequate for personal mode. The layered OS requires the workspace to be the foundation — which requires O3 to land first. Add memory layers after the workspace is live and populated.

**More LLM provider integrations** — `LexConfig` already supports 6 providers via LiteLLM. The model is provider-agnostic. Adding more providers does not improve legal output quality.

**WhatsApp / Slack gateway** — Premature. Telegram is working. New gateways dilute engineering time before the core product (workspace + living agent) is complete.

---

## One-Line Summary

The scaffolding is superb and the vision is correct — the system needs two wire-ups (enqueue path, workspace write) and one loop closure (learning read side) to move from "impressive demo" to "product that improves with use."
