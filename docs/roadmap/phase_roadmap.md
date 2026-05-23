# LexAgent Phase 7–10 Roadmap

**Grounded in:** Phase 6 codebase analysis (architecture_map.md, issues_report.md, impact_radius.md)
**Audience:** Senior engineer starting Phase 7 tomorrow
**Current state:** 245 tests passing, 5 nodes, 1 CLI, 10 tools, 3 skills, 0 gateways

---

## Pre-Phase 7 Critical Fix Sprint (Must Land Before Phase 7 Starts)

These three CRITICAL issues (from issues_report.md) will cause silent data corruption in a
concurrent or production-facing context. Phase 7 (Telegram) introduces concurrency.
Fix all three before writing a single line of Phase 7 gateway code.

### Fix 1 — CRIT-01: Threshold Bypass in `tools/retriever.py` lines 145–151

In `cite.py` line 114, a citation can be marked `verified=True` with near-zero score.
Fix: check `results[0].score >= cfg.retriever_similarity_threshold` before marking verified.
Blast radius: LOW (isolated to cite node, no graph topology change).
Effort: 30 minutes + test.

### Fix 2 — CRIT-02: RAPTOR entries in draft instruction cause `KeyError: 'relevance'`

In `draft.py` lines 156–163, RAPTOR synthetic findings (which have `snippet` not `relevance`,
and `citation=None`) are listed as "Verified case law". Crash when `LEX_RAPTOR_ENABLED=true`.
Fix: filter RAPTOR entries from the instruction loop; inject separately as doctrinal context.
Blast radius: MEDIUM (draft node, raptor_summarizer).
Effort: 1 hour + test.

### Fix 3 — CRIT-03: Matter memory never injected into draft

In `draft.py` lines 196–199, `inject_memory_into_user_turn()` always receives `None`.
`MEMORY.md` is written but never read back for the LLM.
Fix: load `matter_memory.load_matter_memory(matter_id)` in the draft node (or in cli.py
before graph invocation) and pass it to `inject_memory_into_user_turn()`.
Blast radius: MEDIUM (draft node, memory subsystem).
Effort: 1 hour + test.

---

## Phase 7: Telegram Gateway + Contract Review

**Duration:** 3–4 dev-weeks
**Story points:** 42 SP

### Phase Goals

1. A lawyer can send a matter brief via Telegram and receive a formatted draft.
2. A lawyer can upload a PDF contract via Telegram and receive a risk report.
3. The graph compiles once at startup, not per-request (phase 7 concurrency requirement).
4. All CRIT-01/02/03 fixes are live before any user sees output.

### Success Criteria

- `lex gateway telegram start` runs a long-polling bot
- Sending `/draft "injunction brief"` returns a draft within 90 seconds
- Sending a PDF document triggers contract review flow
- Two concurrent Telegram users do not mix state
- All 245 existing tests still pass; 30+ new tests added

### Feature List

| Feature | Priority | SP | Pre-requisites |
|---------|----------|----|---------------|
| Fix CRIT-01 (threshold bypass) | P0 | 2 | — |
| Fix CRIT-02 (RAPTOR injection crash) | P0 | 2 | — |
| Fix CRIT-03 (dead matter memory) | P0 | 3 | — |
| Telegram bot handler (`gateway/telegram.py`) | P0 | 8 | MED-01, MED-02 fixes |
| `build_graph()` singleton at startup | P0 | 2 | graph.py refactor |
| Contract review node (`nodes/contract_review.py`) | P0 | 8 | state.py fields |
| `workflow_mode` routing in graph.py | P0 | 3 | contract review node |
| LexState contract review fields | P0 | 2 | — |
| Intake prompt externalization (HIGH-05 fix) | P1 | 2 | prompts/ dir |
| MED-02 fix: async wrappers in cite + review | P1 | 3 | — |
| MED-01 fix: LexConfig singleton | P1 | 1 | — |
| MED-05 fix: Kanoon browser pool | P1 | 3 | kanoon.py |
| Voice note transcription (faster-whisper) | P1 | 5 | — |
| Telegram session routing (phone → matter_id) | P1 | 3 | session_store.py |
| HIGH-01 fix: wire reranker in cite node | P2 | 2 | reranker.py exists |
| HIGH-04 fix: cause_of_action_date in LexState | P2 | 2 | state.py + intake |

### Critical Path for Phase 7

```
CRIT-01 fix
    → CRIT-02 fix
        → CRIT-03 fix
            → MED-01 fix (config singleton)
            → MED-02 fix (async I/O)
                → graph singleton refactor
                    → telegram.py gateway
                        → session routing
                            → Telegram live test
```

Contract review is parallel to the gateway work after CRIT fixes:
```
LexState contract fields
    → contract_review node
        → workflow_mode graph routing
            → Telegram contract PDF handler
```

### Risk Table

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| IndianKanoon DOM change breaks playwright scraper | HIGH | Add `kanoon_backend=api` path using IK REST API; keep playwright as fallback |
| Telegram long-polling conflicts with asyncio | MEDIUM | Use `python-telegram-bot` v21+ which is fully async; test with `asyncio.run()` |
| SQLite write contention under concurrent Telegram users | HIGH | Enable WAL mode (`PRAGMA journal_mode=WAL`) before Phase 7 goes live |
| LLM response latency exceeds Telegram 90s user expectation | MEDIUM | Stream node progress messages to Telegram; use `graph.astream()` to push updates |
| RAPTOR KeyError on existing matters with saved state | MEDIUM | MED-07 fix (reset raptor_tree on matter resume) must land alongside CRIT-02 |

---

## Phase 8: Hearing + Deadline Intelligence

**Duration:** 3 dev-weeks
**Story points:** 35 SP

### Phase Goals

1. A lawyer sets a hearing reminder via CLI or Telegram; it fires N days before with matter context.
2. The limitation tool actually uses `cause_of_action_date` (HIGH-04 fix enables this).
3. Case timeline tracking: the graph knows what stage a matter is at (FIR, charge sheet, etc.).
4. Filing compliance: court-specific checklists and court fee calculator.

### Success Criteria

- `lex reminder add --matter-id M001 --date 2026-08-15 --note "HC hearing"` stores a job
- Job fires 1 day before with last 500 chars of MEMORY.md injected into reminder
- `lex draft` on a criminal matter prompts for stage (FIR → charge sheet → cognizance → trial)
- `check_limitation` returns real deadline when `cause_of_action_date` is provided

### Feature List

| Feature | Priority | SP | Pre-requisites |
|---------|----------|----|---------------|
| HIGH-04 fix: cause_of_action_date in LexState | P0 | 2 | Phase 7 CRIT fixes done |
| APScheduler job store in sessions.db | P0 | 3 | — |
| `scheduler/reminders.py` | P0 | 5 | APScheduler |
| `lex reminder add / list / delete` CLI | P0 | 3 | reminders.py |
| Telegram reminder delivery | P0 | 2 | Phase 7 gateway live |
| Litigation stage tracker in LexState | P1 | 4 | state.py |
| Stage-aware intake questions | P1 | 3 | intake prompt |
| Procedural next-step detection | P1 | 5 | skill files |
| Limitation deadline alert in review node | P1 | 3 | limitation_analysis |
| Court fee calculator tool | P2 | 5 | tools/registry.py |
| Filing checklist generator | P2 | 5 | skill files |
| CPC/CrPC procedural compliance check | P2 | 5 | new node or skill |

### Critical Path for Phase 8

```
HIGH-04 fix (cause_of_action_date)
    → limitation_tool real dates
        → limitation deadline alerts in review node
```

```
APScheduler setup
    → reminders.py
        → CLI commands
            → Telegram delivery
```

Litigation stage tracker is parallel; depends only on Phase 7 state.py additions.

### Risk Table

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| APScheduler job store schema conflict with existing sessions.db | LOW | Use separate `apscheduler.db` file; avoid mixing with FTS5 tables |
| Hearing date parsing (various formats: "15/08/2026", "Aug 15") | HIGH | Use dateutil.parser with explicit fallback; ask for YYYY-MM-DD in intake |
| Court fee schedules vary by state and year — hardcoding goes stale | HIGH | Store fee tables as YAML under `lexagent/data/court_fees/`; versioned |

---

## Phase 9: Retrieval + Explainability Upgrade

**Duration:** 4 dev-weeks
**Story points:** 48 SP

### Phase Goals

1. Citation chain tracing: show the chain A cites B cites C, flag if C was overruled.
2. Hearing prep: auto-generate a hearing brief (issues, arguments, citations, rebuttals).
3. PageIndex-style hierarchical retrieval: document → section → paragraph.
4. Statute-to-case mapping index: IPC 420 → all verified cases interpreting it.
5. OCR actually works: `pdf_ocr_fallback=True` triggers pytesseract for scanned PDFs.

### Success Criteria

- `lex draft --hearing-prep M001` produces a brief with arguments and rebuttals
- `lex cite-chain "AIR 1978 SC 597"` outputs the citation ancestry graph
- Retrieval precision improvement (qualitative) from hierarchical index
- Scanned PDF uploads (certified copies, FIR copies) produce non-empty text

### Feature List

| Feature | Priority | SP | Pre-requisites |
|---------|----------|----|---------------|
| HIGH-02 fix: OCR fallback actually implemented | P0 | 3 | chunker.py |
| HIGH-01 fix: reranker wired (if not done in Ph7) | P0 | 2 | cite.py |
| Citation chain tracer tool | P1 | 6 | legal_kg.py extension |
| Ratio decidendi extractor | P1 | 5 | new node/tool |
| Hearing prep sub-graph | P1 | 8 | new nodes |
| PageIndex hierarchical index | P1 | 8 | chunker.py + retriever.py |
| Statute-to-case index | P2 | 5 | legal_kg.py + SQLite |
| Opposing argument anticipation | P2 | 5 | hearing prep node |
| Judge profile awareness (SOUL.md extension) | P2 | 4 | soul.py |
| Confidence scoring on citations | P2 | 5 | cite.py |
| WhatsApp gateway (Evolution API) | P3 | 8 | Phase 7 gateway patterns |

### Critical Path for Phase 9

```
HIGH-02 OCR fix
    → scanned PDF ingestion works
        → PageIndex built from real judgments
            → hierarchical retrieval live
```

```
citation chain tracer
    → ratio decidendi extractor
        → hearing prep sub-graph
```

WhatsApp can run in parallel after Phase 7 Telegram is stable.

### Risk Table

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Tesseract quality on Hindi text in court documents | HIGH | Use `lang="hin+eng"` mode; warn lawyer if confidence < 60% |
| Citation chain database too slow for large matters | MEDIUM | Cache traversal results in SQLite; limit chain depth to 5 hops |
| Hearing prep LLM output too generic without real case research | HIGH | Require `research_findings` to be non-empty before hearing prep runs |

---

## Phase 10: Enterprise Readiness + WhatsApp Gateway

**Duration:** 4 dev-weeks
**Story points:** 52 SP

### Phase Goals

1. Multi-lawyer workspace: shared matters, role-based access (senior/junior/paralegal).
2. Full audit trail: every LLM call logged with tokens, model, input hash, output hash.
3. PII detection and redaction before LLM calls.
4. Output versioning: draft v1 → v2 → final with diff view.
5. WhatsApp gateway fully live.
6. Cost tracking per matter (LLM API spend + Kanoon calls).

### Success Criteria

- Two lawyers can share a matter; junior can draft, senior can approve
- `lex audit M001` shows all LLM calls for a matter with token counts
- PII (Aadhaar, phone) detected and replaced with `[REDACTED]` before LLM call
- `lex draft --matter-id M001` on an existing draft shows diff from previous version
- Cost report: "This matter cost ₹120 in LLM API calls"

### Feature List

| Feature | Priority | SP | Pre-requisites |
|---------|----------|----|---------------|
| WhatsApp gateway (Evolution API) | P0 | 8 | Phase 7 Telegram live |
| Multi-lawyer workspace (workspace_id in state) | P1 | 8 | auth model design |
| Audit trail node (wraps every LLM call) | P1 | 6 | new middleware node pattern |
| PII detection pipeline (before draft node) | P1 | 5 | spacy or regex |
| Output versioning in matter_memory | P1 | 4 | matter_memory.py |
| Cost tracking (tokens × price table) | P2 | 4 | _llm.py |
| White-label config (firm name in .docx) | P2 | 3 | docx_writer.py |
| Role-based access control | P2 | 6 | session_store schema |
| Draft diff view in CLI | P2 | 4 | difflib already in stdlib |
| MED-09 fix: SQLite WAL + connection pool | P2 | 3 | session_store.py |
| MED-04 fix: cache TTL + lex cache clear | P3 | 2 | _llm.py |

### Critical Path for Phase 10

```
multi-lawyer workspace
    → audit trail
        → PII detection
            → cost tracking
```

```
WhatsApp gateway
    → session routing (phone → lawyer_id)
        → client isolation tests
```

### Risk Table

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| PII regex misses novel Aadhaar/PAN formats | HIGH | Use spacy NER as secondary; always show lawyer what was redacted |
| Multi-lawyer data isolation bugs | HIGH | Write explicit isolation tests: lawyer A cannot read lawyer B's matters |
| WhatsApp Evolution API rate limits | MEDIUM | Implement message queue with 1-second inter-message delay |
| Output versioning makes state.json large | LOW | Store only diffs, not full snapshots, after v1 |

---

## Engineering Effort Summary

| Phase | Dev-weeks | Story Points | Key Risk |
|-------|-----------|-------------|---------|
| Pre-Ph7 fixes | 0.5 | 7 | Must complete before Phase 7 starts |
| Phase 7 | 3–4 | 42 | SQLite concurrency; Telegram async patterns |
| Phase 8 | 3 | 35 | Court fee data maintenance; date parsing |
| Phase 9 | 4 | 48 | OCR quality; citation chain performance |
| Phase 10 | 4 | 52 | Multi-lawyer data isolation; PII recall |

These are solo-engineer estimates. With two engineers, Phase 7–8 can overlap.

---

## What to Skip (or Defer Beyond Phase 10)

These features from the brief are overengineered for a solo MVP:

1. **Visual workflow builder** — requires a full frontend; build the REST API first (Phase 11)
2. **Judge profile awareness from community data** — community doesn't exist yet; use SOUL.md notes
3. **sqlite-vec for embeddings** — the current BM25+TF-IDF retriever is sufficient through Phase 9;
   add real embeddings only when citation precision becomes measurably inadequate
4. **Multi-document RAPTOR** — fix CRIT-02 first; RAPTOR is currently broken with real use
5. **Opposing counsel pattern memory** — requires large corpus of past matters; irrelevant until Phase 10+
