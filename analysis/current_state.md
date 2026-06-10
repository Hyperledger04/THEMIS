# Current State Analysis

**Investigation date:** 2026-06-09
**Reviewer role:** Principal Systems Architect / Staff Engineer / Product Critic
**Codebase snapshot:** commit `25499912`, branch `main`
**Graph stats:** 237 files · 2,196 nodes · 16,156 edges · 17 communities · 669 tests

---

## 1. Product Hypothesis

LexAgent is trying to become a **persistent legal operating system** for Indian litigation practice. The product bet is: lawyers are drowning in fragmented matter files, missed deadlines, and unverified citations. LexAgent should wake up before the lawyer, process the matter file overnight, and surface court-ready outputs — not just answer questions.

The wedge is the *living matter workspace*: durable, structured legal state that survives chat sessions, graph runs, and gateway switches.

---

## 2. Architecture Understanding

### Execution model (what actually runs)

```
User (CLI / Telegram / Voice / WebSocket)
  → Gateway or Control Plane (FastAPI)
  → LangGraph StateGraph (7 nodes)
      intake → [research | contract_review]
             → retrieve → draft → [cite →] review → END
  → Outputs: draft text, .docx, risk annotations, citation status
  → Persistence: MemorySaver (dev) | AsyncPostgresSaver (prod)
                 SQLite sessions.db
                 ~/.lexagent/SOUL.md + matters/{id}/MEMORY.md
                 optional Qdrant collections
```

### What actually exists (non-trivial code)

| Module | Status | Key files | LOC |
|--------|--------|-----------|-----|
| LangGraph pipeline | **Working** | graph.py, nodes/*.py | ~2,000 |
| LexState | **Working but over-fat** | state.py | 131 |
| LexConfig | **Strong** | config.py | 315 |
| Workspace models | **Designed, partially wired** | workspace/models.py | 277 |
| Workspace repository | **Substantial** | workspace/repository.py | 1,085 |
| Runtime models | **Designed** | runtime/models.py | 139 |
| Runtime worker | **Working skeleton** | runtime/worker.py | 140 |
| Runtime jobs | **One handler only** | runtime/jobs.py | 500 |
| Ingestion | **Working** | ingestion/documents.py, extractors.py | ~600 |
| Security | **Full stack, partially wired** | security/*.py | ~500 |
| Gateway / Control plane | **Working** | gateway/*.py | ~900 |
| Voice gateway | **Working** | gateway/voice.py, gateway/inference.py | ~400 |
| Tools | **Diverse** | tools/*.py (17 tools) | ~3,500 |
| Learning | **Stub-level** | learning/*.py (3 files) | ~434 |
| Agents (personas) | **Personas only** | agents/faces.py, registry.py | ~272 |
| Skills loader | **Working** | skills/loader.py | ~200 |
| Tests | **Extensive** | tests/ (45 files) | ~10,000 |

---

## 3. Current Maturity Assessment

**What is genuinely working:**
- `lex draft "..."` produces a real AI-generated legal draft with citations and .docx output
- Telegram gateway: inline buttons, session persistence, .docx delivery
- Voice gateway: Twilio + WebSocket, STT/TTS, session state
- Contract review: PDF ingestion → clause analysis → risk report
- Citation gate: blocks drafts where citations cannot be verified
- SOUL.md identity injection into every draft
- Per-matter SQLite sessions with reminder tracking
- Security primitives: AES-256-GCM crypto, JWT tokens, RBAC permissions, audit log, PII anonymizer

**What is scaffolded but incomplete:**
- Workspace → graph integration (workspace models exist; graph nodes still write to `LexState` dict, not workspace objects)
- Runtime worker (poll loop works; only `process_uploaded_documents` handler exists)
- Living agent (worker + job models are correct; no morning_brief, research_queue, deadline_scan, risk_analysis, next_actions handlers)
- Learning loop (files exist; no feedback injection into prompts, no preference retrieval at draft time)
- Dynamic planner (no planner.py, executor.py, or event_bus.py anywhere in runtime/)

**What is named but not begun:**
- Chamber subagents (Senior Counsel, Research Counsel, Evidence Counsel, etc.)
- LexMemory OS layered architecture
- Legal Knowledge Graph
- Reflection architecture (multi-pass draft → critic → revision loop)
- Beast Terminal Legal IDE

---

## 4. Intended End-State (V3)

Per `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md` (2026-05-30):

The V3 vision is a **16-phase roadmap** organized around:

1. Durable matter workspace (Postgres, typed objects)
2. 24/7 living agent worker (overnight matter processing)
3. Bulk document intelligence (50+ PDFs → structured matter knowledge)
4. Dynamic planner (LLM-generated execution DAGs per matter type)
5. Specialist chamber subagents (10 counsels coordinated by Senior Counsel)
6. Learning loop (explicit, reviewable, reversible improvement from lawyer edits)
7. Layered memory OS (working / matter / episodic / semantic / procedural / firm / lawyer)
8. Legal Knowledge Layer (corpus partitioning, authority graph, citation verifier)
9. Beast Terminal Legal IDE (Textual-based, subscribes to runtime events)

V3 estimates range from 2-10 weeks per phase. Total scope: ~18-24 months of work.

---

## 5. Hidden Assumptions

### A. Triple identity problem
The codebase simultaneously serves three different product personas:
1. **Teaching platform** — `course/` has 11 pedagogical phases; `CLAUDE.md` says "optimise for clarity over cleverness"
2. **Personal lawyer tool** — CLI, SOUL.md, offline mode, zero-config defaults
3. **Multi-tenant SaaS** — firm_id isolation, RBAC, AES-256-GCM, enterprise hardening

These personas have conflicting requirements. Teaching clarity fights production security. Personal-tool simplicity fights multi-tenancy. No document makes the primary product identity explicit.

### B. The workspace/graph disconnect is architecturally load-bearing
The workspace models (`models.py`) are excellent. The graph nodes still write to `LexState` TypedDict fields. Until nodes start reading from and writing to the workspace (not `LexState`), V3 is a sketch, not a refactor. This gap is never explicitly called out in the roadmap as a migration risk.

### C. Voice is over-indexed relative to legal value
Voice is the highest-criticality flow in the codebase (0.728 per CRG). Voice requires Twilio + STT + TTS + WebSocket infrastructure. A lawyer dictating a writ petition and getting a draft back is compelling, but it's a UI channel — not the core differentiator. The core is the workspace. Voice before workspace is premature channel investment.

### D. Indian Kanoon assumed available
The default for `kanoon_backend` is `"stub"`. The real API is gated by key. Tests mock it. The whole research quality hypothesis depends on Indian Kanoon being accessible, fast, and returning structured judgment text. This is never stress-tested with real volume.

### E. 16 phases will not stay sequential
The roadmap presents phases 1→16 as sequential. The current code shows phases 1, 2, 3, 4, 5, and 6 started simultaneously in interleaved commits. This is realistic but means no phase is truly "done" before the next begins. Quality debt accumulates silently.

---

## 6. Key Questions This Repository Raises

- What is this trying to become? → A persistent legal OS for Indian litigation
- What already exists? → A solid LangGraph chatbot/agent that can draft documents, with a comprehensive V3 design layered on top as mostly-implemented scaffolding
- What appears unfinished? → Chamber subagents, planner, event bus, living agent job handlers, learning injection, workspace→graph wiring
- What seems overengineered? → Voice gateway (premature), 16-phase roadmap horizon (too far out to be useful day-to-day), `LexState` with 57 fields
- What is unexpectedly strong? → Workspace models (§11A failure modes are explicitly addressed), LexConfig discipline (80 fields, all-off defaults), security package completeness, test density (669 tests, 45 files)
