# LexAgent V3 — Complete Architecture & Build Sequence

**Status:** Design locked. Implementation in progress.
**Date:** 2026-06-23
**Source:** Grilling session (22 locked decisions) + architectural synthesis (19-section roadmap) — merged into one authoritative document.
**Supersedes:** `LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md`, prior `V3_ARCHITECTURE.md`

---

## 0. Product Pivot

LexAgent transitions from **chat session with a graph** to a **living matter workspace**.

The agent keeps working while the lawyer is offline. It wakes before the lawyer, processes the matter file, drafts next documents, identifies risks, and says what needs to be done next. The matter — not the session — is the core primitive.

### What LexAgent Is Today

A LangGraph-based Indian legal workflow agent. It can intake a brief, run a mostly linear research path, draft, verify citations, review, persist some memory, expose a FastAPI control plane, support Telegram/voice gateways, run contract review, store sessions in SQLite, and optionally checkpoint LangGraph state in Postgres.

It has real primitives: `LexState`, `StateGraph`, node contracts, tool registry, skills, lawyer/matter memory, control plane, voice gateway, research APIs, citation gate, security scaffolding, tests, and config discipline.

### What It Is Pretending To Be

- The control plane still uses a static bearer secret rather than the security package.
- Multi-tenant config exists but session/reminder isolation is not enforced.
- Memory is mostly file/session based, not a canonical matter workspace.
- The graph is static and workflow-centric.
- The "ReAct research" node is API-first but not an autonomous investigation loop.
- The scheduler is reminder-specific, not a general proactive runtime.

### What It Must Become

1. A durable legal matter state model.
2. A 24/7 living agent that keeps working on matters while the lawyer is offline.
3. Bulk document intelligence for PDFs, images, scanned copies, emails, and KB files.
4. A dynamic planner that creates execution DAGs per goal.
5. A legal runtime that schedules, resumes, audits, and supervises long-running work.
6. A learning loop that improves drafting, research, and skills from lawyer feedback.
7. A legal memory OS with separate working, matter, episodic, semantic, procedural, firm, and lawyer memories.
8. Specialist legal subagents coordinated by a Senior Counsel agent, with verification gates before output leaves the system.
9. Thin gateways and a rich terminal/web legal IDE that view and control the same runtime.

---

## 1. Locked Decisions (22)

These 22 decisions are final. No open questions.

| # | Decision | Choice | Reason |
|---|---|---|---|
| 1 | Strategic direction | V3 matter workspace first | Session model creates debt that R1–R11 on top compounds |
| 2 | Canonical matter store | Postgres | Structured query, FK for docs/events, already in docker-compose |
| 3 | Semantic layer | Qdrant on top of Postgres | Postgres = source of truth, Qdrant = similarity search |
| 4 | Agent runtime | ARQ + Redis | True async, built-in retry, pub/sub for real-time updates |
| 5 | Runtime fallback | Postgres | Worker startup scans for paused matters if Redis is lost |
| 6 | State sync | LangGraph checkpointer (graph) + `persist_matter()` (business) | Different concerns, don't conflate |
| 7 | Agent architecture | LangGraph multi-agent via `send()` | Lavern (R9) is real; retrofitting later = double refactor |
| 8 | Specialist roster | 4 specialists + Senior Counsel | Researcher, Drafter, Reviewer, Verification |
| 9 | State design | Scoped child TypedDict per specialist | Clean boundaries, testable in isolation, Lavern-compatible |
| 10 | Messages | Scoped `thread_messages` per specialist, clean narrative in parent | Audit trail for evals + reverse-engineering specialist output |
| 11 | Senior Counsel planning | Rule-based defaults + LLM override + whitelist | Novel matters handled, hallucinated specialists blocked |
| 12 | Researcher tool routing | LLM-routed (ReAct agent decides which tool) | Covers cases cascade misses; cheaper than fan-out |
| 13 | Citation gate | Flag unverified, pass through with tag, human interrupt | Silent drop is dangerous; retry loop is fragile |
| 14 | Verification browser stack | browser-use + Stagehand + Skyvern + Bright Data MCP | Anti-bot, structured extraction, form-based courts |
| 15 | VerificationAgent placement | 4th specialist subgraph | Runs in separate ARQ job post-interrupt — subgraph boundary by definition |
| 16 | Memory ownership | Senior Counsel owns all reads and writes | Single writer; scales to 67 Lavern agents without race conditions |
| 17 | Qdrant indexing | Hybrid — judgments sync (Drafter needs them same run), summaries/feedback async | Balances latency vs freshness |
| 18 | Multi-tenancy | `firm_id` + Postgres RLS from day one | 3-line SQL policy now vs dangerous live migration later |
| 19 | Agent registry | Code-defined Python dict (Lavern pattern) | `definitions.py` + `profiles.py` + `enrich_prompt()` |
| 20 | Debate board | MCP server (`mcp__lex__`) | Errors caught at finding level, not final draft |
| 21 | Model assignment | User-configurable via `LexConfig`, defaults in `agent_profiles` | Lawyer controls cost/quality trade-off |
| 22 | `next_action` format | Structured JSON: `{"node": "...", "params": {...}}` | ARQ worker can deserialise and invoke directly, no LLM step |

---

## 2. Current Architecture Audit

```
User
  |
  | CLI / Telegram / Voice / WebSocket / REST
  v
Gateway or Control Plane
  |
  | builds LexState + thread_id
  v
LangGraph StateGraph
  |
  v
intake → research/react_research → draft → cite → review
                                                      |
                                                      v
                                                   Outputs
  Persistence:
    LangGraph MemorySaver / AsyncPostgresSaver
    SQLite sessions.db + reminders + chat_messages
    ~/.lexagent/SOUL.md
    ~/.lexagent/matters/{matter_id}/MEMORY.md + state.json
    optional Qdrant collections
    judgment cache under ~/.lexagent/judgments
```

### Current Bottlenecks

1. Workflow-centric design: graph encodes document generation, not legal operations.
2. Static graph: adding new workflows bloats conditional edges and `LexState`.
3. No planner: cannot generate different DAGs for writ vs NI Act vs arbitration.
4. Weak runtime: no job model, event bus, run lifecycle, pause/resume, durable task queue.
5. No living agent: does not keep working overnight or proactively prepare matters.
6. No bulk document intelligence: 50+ PDFs cannot become a chronology automatically.
7. Weak memory boundaries: file memory, session memory, and checkpoint memory overlap.
8. No explicit learning loop: lawyer edits and repeated workflows are not reused.
9. Security scaffolding not wired: packages exist but control plane does not enforce them.
10. Research is retrieval-heavy: searches and fetches; does not investigate.
11. Verification is underpowered: citation gate prevents worst errors but not legal invalidity.

### Gap Scores (OpenClaw benchmark)

| Dimension | Score | Gap |
|---|---|---|
| Runtime | 3/10 | No job lifecycle, event loop, cancellation, approvals, retries, durable queues |
| Gateway | 5/10 | Exists but CORS wildcard + static token; not truly thin |
| Events | 1/10 | Reminders only; no domain event bus |
| Memory | 4/10 | Useful local memory but no canonical matter workspace |
| Skills | 5/10 | Markdown loader is elegant; needs manifests, versioning, evals |
| Subagents | 2/10 | Personas exist; not operational specialist subagents with contracts |
| Agent lifecycle | 2/10 | No run/job state machine |
| Long-running execution | 2/10 | Postgres checkpointing helps but no background runtime |
| Autonomy | 3/10 | Some auto modes; no planner + event-driven proactive behavior |

---

## 3. Storage Architecture

```
┌─────────────────────────────────────────────────────┐
│                   LexAgent Storage                  │
│                                                     │
│  Postgres (canonical)                               │
│  ├── matters          ← business state, RLS         │
│  ├── firms, lawyers   ← identity                    │
│  ├── documents        ← file metadata               │
│  ├── checkpoints      ← LangGraph graph state       │
│  └── reminders, sessions (existing)                 │
│                                                     │
│  Qdrant (semantic layer)                            │
│  ├── judgments        ← chunked, sync indexed       │
│  ├── matters          ← summary embeddings, async   │
│  └── lawyer_feedback  ← learning loop, async        │
│                                                     │
│  Redis                                              │
│  └── ARQ job queue    ← matter jobs, worker pool    │
└─────────────────────────────────────────────────────┘
```

**Rule:** Postgres = source of truth for business state. LangGraph checkpointer = run-mechanical state only (resume-this-run, not query-all-facts). Qdrant = similarity search on top. Redis = async decoupling.

### Qdrant Corpus Partitioning

All sources must be tagged at indexing time. Never mix corpora in a single collection without partition metadata.

| Namespace | Contents |
|---|---|
| `corpus:india_sc` | Supreme Court of India |
| `corpus:india_hc:{state}` | High Courts, per state |
| `corpus:india_subordinate` | District / Tribunal level |
| `corpus:privy_council` | Privy Council (pre-Independence persuasive) |
| `corpus:foreign_persuasive` | UK, Singapore, Australia, etc. |
| `corpus:statutes` | Indian statutes and rules |
| `corpus:regulations` | Notifications, circulars, SROs |
| `corpus:firm_docs` | Uploaded matter documents, templates, precedents |

---

## 4. Matter Table Schema

```sql
CREATE TYPE matter_status AS ENUM (
    'intake', 'researching', 'drafting', 'reviewing',
    'awaiting_approval', 'verifying', 'complete', 'paused', 'error'
);

CREATE TABLE matters (
    -- Identity
    matter_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    firm_id         UUID NOT NULL REFERENCES firms(firm_id),
    lawyer_id       UUID NOT NULL REFERENCES lawyers(lawyer_id),
    title           TEXT NOT NULL,
    matter_type     TEXT NOT NULL,         -- 'ni_act_138', 'bail', 'injunction', etc.
    jurisdiction    TEXT NOT NULL,
    parties         JSONB NOT NULL,        -- [{role: 'complainant', name: '...', ...}]

    -- Workflow
    status          matter_status NOT NULL DEFAULT 'intake',
    next_action     JSONB,                 -- {"node": "research", "params": {...}}
    priority        INT DEFAULT 5,
    deadline        DATE,

    -- Semantic (mirrored to Qdrant async)
    summary         TEXT,
    key_facts       JSONB DEFAULT '[]',
    statutes_cited  JSONB DEFAULT '[]',
    risk_score      FLOAT,

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row-Level Security — every query scoped to firm automatically
ALTER TABLE matters ENABLE ROW LEVEL SECURITY;
CREATE POLICY firm_isolation ON matters
    USING (firm_id = current_setting('app.firm_id')::UUID);
```

**`parties` JSONB shape:**
```json
[
  {"role": "complainant", "name": "Ankush Sareen", "counsel": "Self"},
  {"role": "accused", "name": "XYZ Ltd", "counsel": "Adv. Sharma"},
  {"role": "bank", "name": "HDFC Bank", "branch": "Connaught Place"}
]
```

**`next_action` JSONB shape:**
```json
{"node": "research", "params": {"focus": "limitation period S.138 NI Act"}}
```

### Full Matter Workspace Objects (Postgres tables)

Beyond the `matters` table, the complete workspace requires:

- `parties`, `facts`, `issues`, `documents`, `document_chunks`
- `chronology_items`, `evidence_items`, `authorities`, `research_sessions`
- `drafts`, `deadlines`, `tasks`, `verification_reports`
- `feedback_items`, `style_preferences`, `playbook_notes`
- `debate_board` (for MCP server)
- `jobs`, `events` (for runtime)

**Rule:** JSONB only for flexible metadata, not primary legal facts. Every mutation emits a domain event. Drafts are immutable versions; edits create a new version. Soft delete + audit on deletions.

### Pydantic Models (for typed workspace objects)

```python
class Provenance(BaseModel):
    source_type: Literal["user", "document", "agent", "court", "research"]
    source_id: str | None = None
    quote: str | None = None
    confidence: float = 1.0

class Fact(BaseModel):
    id: str
    matter_id: str
    text: str
    status: Literal["alleged", "admitted", "disputed", "proved", "unknown"]
    date: date | None = None
    provenance: list[Provenance]

class Authority(BaseModel):
    id: str
    type: Literal["case", "statute", "regulation", "circular", "order"]
    title: str
    citation: str | None = None
    court: str | None = None
    url: str | None = None
    proposition: str
    jurisdiction: str           # "india", "uk", "singapore", etc.
    country: str
    court_tier: Literal["binding_sc", "binding_hc", "persuasive_domestic", "persuasive_foreign", "academic"]
    corpus_namespace: str       # e.g. "corpus:india_sc"
    treatment: Literal["binding", "persuasive", "distinguished", "overruled", "unknown"]
    verified_excerpt: str | None = None   # exact quote from source text
    paragraph_number: str | None = None
    verification_status: Literal["verified", "partial", "contradicted", "unverified"] = "unverified"
    verified: bool = False

class Draft(BaseModel):
    id: str
    matter_id: str
    doc_type: str
    version: int
    content: str
    status: Literal["draft", "under_review", "approved", "filed"]
    verification_report_id: str | None = None

class ChronologyItem(BaseModel):
    id: str
    matter_id: str
    date: date | None = None
    date_text: str
    event: str
    source_document_id: str | None = None
    provenance: list[Provenance]
    confidence: float = 0.0

class FeedbackItem(BaseModel):
    id: str
    matter_id: str | None = None
    user_id: str
    target_type: Literal["draft", "research", "authority", "risk", "skill", "checklist"]
    target_id: str | None = None
    signal: Literal["accepted", "rejected", "edited", "preferred", "corrected"]
    note: str | None = None
    diff: str | None = None
```

---

## 5. State Schema

### 5.1 Senior Counsel Parent State

```python
# themis/state.py  (replaces current LexState)
from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages

class SeniorCounselState(TypedDict):
    # Matter identity
    matter_id:          str
    firm_id:            str
    lawyer_id:          str
    matter_type:        str
    jurisdiction:       str
    parties:            list[dict]
    purpose:            str

    # Planning
    execution_plan:     list[dict]   # [{"specialist": "researcher", "params": {...}}]
    active_specialist:  Optional[str]

    # Inter-agent handoff slots
    research_findings:  list[dict]   # populated by ResearcherAgent
    draft_output:       Optional[str]
    review_result:      Optional[dict]
    verification_result: Optional[dict]

    # Memory (Senior Counsel reads/writes, specialists never touch)
    lawyer_soul:        Optional[str]
    matter_memory:      Optional[str]

    # Conversation (lawyer-facing narrative only)
    messages:           Annotated[list, add_messages]

    # Persistence
    status:             str
    next_action:        Optional[dict]

    # Meta
    error:              Optional[str]
```

### 5.2 Specialist Child States

```python
class ResearcherState(TypedDict):
    matter_id:          str
    matter_type:        str
    jurisdiction:       str
    parties:            list[dict]
    purpose:            str
    search_queries:     list[str]
    tool_calls_log:     list[dict]
    research_findings:  list[dict]   # [{title, citation, doc_excerpt, url, verified: bool}]
    statutes_cited:     list[str]
    limitation_analysis: Optional[str]
    thread_messages:    list[dict]   # internal audit trail

class DrafterState(TypedDict):
    matter_id:          str
    matter_type:        str
    jurisdiction:       str
    parties:            list[dict]
    research_findings:  list[dict]
    lawyer_soul:        Optional[str]
    active_skill:       Optional[str]
    draft_output:       Optional[str]
    plain_english_summary: Optional[str]
    risk_annotations:   list[dict]
    thread_messages:    list[dict]

class ReviewerState(TypedDict):
    matter_id:          str
    draft_output:       str
    research_findings:  list[dict]
    matter_type:        str
    review_result:      dict         # {passed: bool, issues: [...], risk_score: float}
    unverified_citations: list[dict]
    citations_verified: bool
    thread_messages:    list[dict]

class VerificationState(TypedDict):
    matter_id:          str
    unverified_citations: list[dict]  # [{title, citation, doc_excerpt, url}]
    lawyer_approved:    bool
    verification_result: dict        # {verified: [...], failed: [...], confidence: {}}
    thread_messages:    list[dict]
```

**Rule:** `LexState` is ephemeral run context. `Matter Workspace` tables are permanent. Every node that reads or writes legal facts should reference Workspace objects by ID, not carry the data itself in state.

---

## 6. Agent Architecture

### 6.1 Graph Structure

```
                    ┌──────────────────────────────┐
                    │       Senior Counsel          │
                    │                               │
                    │  intake → plan → coordinate   │
                    │       ↓                       │
                    │  persist_matter()             │
                    └──────────┬───────────────────┘
                               │ send()
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
      ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
      │  Researcher  │ │   Drafter   │ │   Reviewer   │
      │  Agent       │ │   Agent     │ │   Agent      │
      │  subgraph    │ │   subgraph  │ │   subgraph   │
      └──────────────┘ └─────────────┘ └──────────────┘
                                                │
                              unverified        │ interrupt()
                              citations ────────┘
                                   │
                              lawyer approves
                                   │
                         ┌─────────────────────┐
                         │  Verification Agent │
                         │  subgraph           │
                         │  (separate ARQ job) │
                         └─────────────────────┘
```

### 6.2 Agent Registry (Lavern Pattern)

```
themis/agents/
├── definitions.py      # agent_definitions dict — name → {description, prompt, tools, model, max_turns, output_format}
├── profiles.py         # agent_profiles dict — name → {skills, critical_rules, success_metrics, default_model}
├── prompts/
│   ├── senior_counsel.py
│   ├── researcher.py
│   ├── drafter.py
│   ├── reviewer.py
│   └── verification.py
└── tool_arrays.py      # read_only_tools, debate_tools, memory_read_tools, verification_tools
```

**`enrich_prompt()` — appended to every agent's base prompt:**
```
## Critical Rules (NEVER violate these)
- [from profile.critical_rules]

## Success Metrics (your output is measured by these)
- [from profile.success_metrics]

## When You Are Not Sure
If you cannot make a confident determination, use the `decline_to_find` tool
instead of posting a finding. A declined finding triggers human review.
A wrong finding causes harm. Confidence threshold: 0.5.
```

**Tool arrays:**
```python
read_only_tools    = ["read_file", "search_kb", "list_matter_docs"]
debate_tools       = ["post_finding", "decline_to_find", "post_challenge",
                      "post_response", "get_findings", "get_debate_summary",
                      "get_unresolved_debates"]
memory_read_tools  = ["query_matter_memory", "query_lawyer_profile", "query_precedents"]
memory_write_tools = ["save_matter_memory", "save_precedent"]  # Senior Counsel only
verification_tools = ["run_citation_verification", "run_cross_verification"]
browser_tools      = ["browser_use_navigate", "stagehand_extract",
                      "skyvern_act", "brightdata_fetch"]
```

**Model assignment — user-configurable:**
```python
# defaults in agent_profiles.py, overridden via LexConfig
SENIOR_COUNSEL_MODEL  = "claude-opus-4-8"
RESEARCHER_MODEL      = "claude-sonnet-4-6"
DRAFTER_MODEL         = "claude-opus-4-8"    # draft is the product
REVIEWER_MODEL        = "claude-sonnet-4-6"
VERIFICATION_MODEL    = "claude-sonnet-4-6"
```

### 6.3 Senior Counsel Planning Logic

```python
# Rule-based defaults (covers 90% of Indian litigation)
MATTER_TYPE_PLANS = {
    "ni_act_138":      [{"specialist": "researcher"}, {"specialist": "drafter"}, {"specialist": "reviewer"}],
    "bail":            [{"specialist": "researcher"}, {"specialist": "drafter"}, {"specialist": "reviewer"}],
    "injunction":      [{"specialist": "researcher"}, {"specialist": "drafter"}, {"specialist": "reviewer"}],
    "contract_review": [{"specialist": "reviewer"}],
    "quick_research":  [{"specialist": "researcher"}],
}

# LLM override for novel matter types
# Planner receives agent_definitions descriptions, outputs plan validated against whitelist
SPECIALIST_WHITELIST = {"researcher", "drafter", "reviewer", "verification"}
```

### 6.4 Full Chamber Vision (Phase 11)

The V3.3 build delivers the 4-specialist MVP. The full chamber (Phase 11) expands to 9 specialist counsels:

- **Senior Counsel** — owns final answer, delegates, resolves conflicts, enforces verification gates
- **Planner Counsel** — converts goal into execution DAG and required matter objects
- **Research Counsel** — case law, precedents, treatment, negative authorities
- **Statutory Counsel** — acts, rules, regulations, notifications, circulars
- **Procedure Counsel** — jurisdiction, limitation, maintainability, forum, court fees
- **Evidence Counsel** — documents, chronology, admissions, gaps, exhibit mapping
- **Drafting Counsel** — pleadings, notices, contracts, affidavits, applications, bundles
- **Citation Counsel** — verifies citations, source text, page references, treatment history
- **Risk Counsel** — attacks the draft, finds weak facts, adverse law, procedural objections

---

## 7. Debate Board MCP Server

```
mcp__lex__ server — runs as a sidecar in docker-compose

Tools exposed to all agents:
  post_finding(agent_id, finding_text, confidence, evidence_refs)
  decline_to_find(agent_id, reason, matter_area)
  post_challenge(agent_id, finding_id, challenge_text)
  post_response(agent_id, challenge_id, response_text)
  get_findings(matter_id, status?)
  get_debate_summary(matter_id)
  get_unresolved_debates(matter_id)

Storage: Postgres `debate_board` table (matter_id FK, scoped by RLS)
```

**Flow:** ResearcherAgent posts findings → ReviewerAgent challenges weak ones → debate resolves → DrafterAgent sees only resolved, high-confidence findings. Errors are caught at the finding level, not the final draft.

---

## 8. Citation Gate Flow

```
ResearcherAgent finds a judgment
    ↓
Gate check: does finding have {title, citation, doc_excerpt, url}?
    ↓ NO
Tag: {"verified": false, "reason": "missing_citation", "finding": {...}}
Pass through to SeniorCounselState.research_findings
    ↓
ReviewerAgent flags unverified citations
    ↓
Senior Counsel calls LangGraph interrupt()
    ↓
Lawyer notified: "3 citations unverified. Allow browser verification? [Yes/No]"
    ↓ YES
Matter status → "awaiting_approval" in Postgres
ARQ enqueues verify_citations_job(matter_id)
    ↓
VerificationAgent subgraph runs in fresh ARQ job
browser-use / Stagehand / Skyvern search Indian court sites
Results: {verified: [...], failed: [...]}
    ↓
Senior Counsel merges results, updates research_findings
Graph resumes → Drafter receives clean findings
```

**Verification status is tri-state — never binary:**
- `verified` — excerpt matches proposition
- `partial` — case real, proposition unconfirmed
- `contradicted` — case says the opposite

**Block final output on `contradicted`. Flag `partial` explicitly in draft and report.**

---

## 9. Memory Architecture

### 9.1 Layers

```
LexMemory OS
  Working Memory     current run context, DAG node state, active facts
  Matter Memory      canonical matter workspace and lifecycle
  Episodic Memory    conversations, hearings, orders, research sessions
  Semantic Memory    cases, statutes, principles, issue graph, firm KB
  Procedural Memory  playbooks, skills, filing checklists, court practices
  Firm Memory        institutional templates, preferences, court/judge knowledge
  Lawyer Memory      style, bar profile, preferred arguments, risk tolerance
```

### 9.2 Ownership Rules

- **Senior Counsel** owns all memory reads and writes.
- Specialists receive memory as typed input fields in their child state.
- Specialists **never call mem0 or Postgres directly** for memory operations.
- Single writer scales to 67 Lavern agents without race conditions.

### 9.3 Current → V3 Migration

| Current | V3 |
|---|---|
| `~/.themis/SOUL.md` | Lawyer layer — SOUL.md now, mem0 in R2B |
| `~/.themis/matters/{id}/MEMORY.md` | Matter layer — MEMORY.md now, mem0 in R2B |
| `sessions.db` SQLite | Episodic layer — SQLite now, mem0 in R2B |

---

## 10. Research System

### 10.1 Investigation Agent Process

```
Plan
  → Search
  → Read
  → Extract propositions
  → Form hypotheses
  → Search again for support/adverse law
  → Compare authorities
  → Verify citations
  → Conclude with confidence and gaps
```

### 10.2 Sources

| Source | Use |
|---|---|
| Indian Kanoon | Broad case law search and fetch |
| eCourts | Matter status, orders, cause list |
| Gazette | Notifications and amendments |
| MCA | Companies, filings, charges |
| SEBI | Orders, circulars, enforcement |
| RBI | Master directions, circulars, FAQs |
| Tavily | Open web fallback |
| SCC/paid databases | Connector-ready, not assumed |

### 10.3 Citation Verification Pipeline

1. Parse citation and authority title.
2. Fetch source text from primary source.
3. Extract the ratio decidendi paragraph(s) — not just case existence.
4. Compare drafted proposition against extracted excerpt (citation drift check).
5. Verify paragraph/page reference.
6. Check court hierarchy, jurisdiction, and binding value (jurisdictional conflation check).
7. Check treatment: overruled, distinguished, followed, pending appeal.
8. Produce `CitationVerification` object with status `verified` / `partial` / `contradicted`.
9. Block final output on `contradicted`. Never collapse to binary pass/fail.

---

## 11. Practitioner Failure Modes

*Source: AI governance advisor with practitioner validation. Surface under real litigation pressure.*

### Failure Mode 1: Citation Drift

**What:** The model retrieves the correct case but misreads or misrepresents the ratio decidendi. The citation is real; the proposition attributed to it is not.

**Why dangerous:** A lawyer submits a pleading citing *Kesavananda Bharati* for a proposition it does not stand for. Court rejects the argument.

**Design response:**
- Citation verification must include ratio extraction: pull the specific paragraph(s), not just confirm case existence.
- Store `verified_excerpt`, `paragraph_number`, and `proposition_stated` in `Authority` records.
- Compare drafted proposition against the extracted excerpt.
- Verification status must be tri-state: `verified`, `partial`, `contradicted`.
- Block on `contradicted`. Flag `partial` in draft and verification report.

### Failure Mode 2: Jurisdictional Conflation

**What:** Indian and foreign precedents share retrieval corpora. The model presents a Privy Council or Singapore Court of Appeal judgment as persuasive Indian authority without flagging different binding weight.

**Why dangerous:** Indian courts apply strict hierarchy — SC binds all; HCs bind within territory; foreign cases are persuasive only. Conflation embarrasses the filing lawyer.

**Design response:**
- Every `Authority` record must carry `jurisdiction`, `court_tier`, and `country`.
- Tag corpus provenance at **indexing time**, not retrieval time.
- Prompt for drafting node receives authorities pre-separated by tier: binding SC/HC, persuasive domestic, persuasive foreign — with explicit treatment instructions per tier.
- Critic pass must check: are any foreign authorities cited as binding? Flag as procedure defect if so.
- Jurisdictional corpus separation is a **retrieval architecture requirement**, not a prompt instruction.

### Failure Mode 3: Confidentiality Bleed

**What:** In multi-client workflows, facts, strategies, and drafted text from one matter surface in another — through shared vector embeddings, shared retrieval collections, or shared in-memory research caches.

**Why dangerous:** Legal professional privilege is absolute. A single bleed event terminates the firm relationship and invites bar council action.

**Design response:**
- Matter-level isolation is mandatory. Every Postgres query touching facts, documents, authorities, drafts, or research must include `matter_id` AND `firm_id` predicates.
- Qdrant collections must be partitioned per matter or per firm. Never shared across the platform.
- In-process research caches must be scoped to current `thread_id` / `matter_id` and garbage-collected at run end.
- LangGraph checkpointer state must be keyed by `(thread_id, matter_id)`. Sharing a `thread_id` across matters is a bleed vector.
- SOUL.md must not be injected into prompts for matters belonging to a different firm in multi-tenant mode.
- Add `test_matter_isolation.py`: create two matters, populate each with distinct facts, run research on matter A, assert that retrieved context contains zero `Fact` or `Authority` objects from matter B.

---

## 12. Adversarial Review Architecture

### 12.1 Chamber MVP (ships now — doc-haus bridge pattern)

Three sequential LLM calls in `themis/nodes/chamber.py`. No subagent contracts needed. Full §6.4 chamber replaces this node in Phase 11 with identical external interface.

```
draft_output
  → Reviewer LLM  → chamber_issues (numbered issue list)
  → Challenger LLM (sees issues + draft) → chamber_pushback (VALID / OVERSTATED / WRONG per item)
  → Summarizer LLM (sees all) → chamber_review (action items + RISK LEVEL)
```

Review dimensions: legal validity, authorities, procedure, logic, persuasiveness, citation accuracy, risk to client, missing facts/evidence.

Activation: `--chamber` CLI flag OR automatic when `matter_type == "contract_review"`.
Graph insertion: conditional edge `draft → chamber → review`.

### 12.2 Full Reflection Architecture (Phase 12)

```
Draft
  → Critic: legal validity → Revision
  → Critic: authorities and citation accuracy → Revision
  → Critic: procedure and maintainability → Revision
  → Critic: logic and persuasiveness → Senior Counsel approval
```

The verification report must be stored with every draft version.

---

## 13. Event-Driven Runtime

### 13.1 Domain Events

```
NEW_DOCUMENT, DOCUMENT_PROCESSED, NEW_FACT, NEW_CHRONOLOGY_ITEM,
NEW_HEARING, NEW_PRECEDENT, LIMITATION_WARNING, CLIENT_MESSAGE,
EMAIL_RECEIVED, COURT_ORDER, TASK_DUE, DRAFT_APPROVED,
AUTHORITY_OVERRULED, FEEDBACK_RECEIVED, MORNING_BRIEF_READY
```

Every event carries: `event_id`, `firm_id`, `matter_id`, `actor`, `type`, `payload`, `created_at`, `causation_id`, `correlation_id`.

### 13.2 Subscribers

```
Event Bus
  → Planner
  → Living Agent Worker
  → Document Processor
  → Chronology Builder
  → Deadline Radar
  → Research Watcher
  → Matter Workspace Projector
  → Notification Dispatcher
  → Audit Logger
  → UI Live Updates
```

### 13.3 Implementation Phases

- **V3.4 (MVP):** Postgres event table + async in-process dispatcher. Postgres `jobs` table. One `lex worker` process.
- **Phase 3:** APScheduler for cron publishers.
- **Later:** Redis Streams or NATS when multi-process scaling is needed.

### 13.4 ARQ Worker Jobs

```python
# themis/worker/jobs.py

@worker.task
async def run_matter_job(matter_id: str, firm_id: str):
    await db.execute(f"SET app.firm_id = '{firm_id}'")
    matter = await db.get_matter(matter_id)
    config = {"configurable": {"thread_id": matter_id}}

    if matter.status == "paused" and matter.next_action:
        await graph.ainvoke(matter.next_action["params"], config=config)
    else:
        await graph.ainvoke(initial_state_from_matter(matter), config=config)

@worker.task
async def index_matter_job(matter_id: str):
    matter = await db.get_matter(matter_id)
    await qdrant.upsert_matter_summary(matter)

async def recover_paused_matters():
    paused = await db.query("SELECT matter_id, firm_id FROM matters WHERE status = 'paused'")
    for m in paused:
        await worker.enqueue(run_matter_job, m.matter_id, m.firm_id)
```

### 13.5 Living Agent MVP Job Types

```
process_uploaded_documents → extract_facts_and_issues → build_chronology
→ build_evidence_table → create_research_memo → create_risk_analysis
→ deadline_scan → morning_brief → next_actions → draft_next_document
```

**Approval rule:** The living agent may read, summarize, extract, draft, analyze, and recommend. It must **not** file, send emails/notices, message clients, or mutate external systems without explicit lawyer approval.

### 13.6 Bulk Document Intelligence (Phase 4)

1. Store original file with matter ID and provenance.
2. Extract text with `pdfplumber` where possible; OCR fallback for scanned files.
3. Chunk text and save `document_chunks`.
4. Extract dates, parties, amounts, courts, document types, key events.
5. Build chronology and evidence table.
6. Link every extracted fact/date to source document/page.
7. Queue research memo, risk memo, next actions, and draft jobs.

**Grid Analysis (ships in doc-haus bridge, before Phase 4):**
```
lex grid <matter_id> --questions "Q1" "Q2" --csv output.csv
  → _list_matter_docs(matter_id)
  → asyncio.gather(_run_qa(q, doc) for q in questions for doc in docs)
  → {question: {doc_name: answer}} → Rich table + optional CSV
```
When Phase 4 ingestion ships, `_list_matter_docs` is swapped for a workspace repository query — same node, no interface change.

---

## 14. Planner Architecture

```
Goal + Matter Workspace + Policy
  → Planner Counsel
  → ExecutionDAG(nodes, dependencies, required_inputs, tools, approval_gates)
  → Runtime schedules nodes
  → Agents execute nodes
  → Events update workspace
```

### Example DAGs

**NI Act Section 138:**
```
document_checklist → cheque/date/return_memo/notice/timeline extraction
→ limitation/statutory compliance → accused/company liability analysis
→ complaint_draft → evidence_bundle → verification
```

**Writ Petition:**
```
intake → maintainability → alternative_remedy_analysis → rights/statute research
→ evidence_timeline → grounds → prayer → draft_petition
→ procedure_review → citation_verification → risk_attack → revision
```

**Contract Review:**
```
contract_ingest → clause_map → risk_playbook → deviation_analysis
→ negotiation_positions → redline → executive_summary
```

**MVP simplification:** Start with template plans for legal notice, writ, NI Act S.138, arbitration, and contract review. Add LLM-generated plans only after template execution is stable.

---

## 15. Learning Loop

### 15.1 Learning Signals

- Lawyer edits to drafts (diff stored in `feedback_items`)
- Accepted/rejected authorities
- Preferred clauses and argument structures
- Jurisdiction-specific checklist notes
- Repeated workflow patterns
- Feedback ratings and corrections

### 15.2 Rules

- Store feedback in `feedback_items`, `style_preferences`, `playbook_notes`.
- Use records in future prompts and planner templates.
- **Suggest** skill/playbook updates; **never silently rewrite** core prompts.
- Learning records must be explicit, reviewable, and reversible.

---

## 16. Security Architecture

### 16.1 Required Final State

- Dual mode: personal mode zero-friction; enterprise mode enforced.
- JWT access token, refresh rotation, API keys.
- RBAC matrix: admin, partner, associate, viewer.
- Tenant isolation on every Postgres/SQLite/Qdrant/object-store query.
- AES-256-GCM at rest with HKDF per-firm keys (not Fernet — resolved contradiction from `Security_features.md`).
- TLS enforcement and secure headers in enterprise mode.
- Audit log with 7-year retention.
- Rate limits and budget caps.
- GDPR/DPDP export and erasure workflows.
- CORS wildcard forbidden in enterprise mode.

### 16.2 Matter-Level Confidentiality (Failure Mode 3 implementation)

- Every query touching facts, documents, authorities, drafts, research, chronology, or feedback must include both `firm_id` AND `matter_id` predicates. No exceptions.
- Qdrant collections must be namespaced per firm or per matter.
- LangGraph checkpointer state keyed by `(thread_id, matter_id)`.
- In-process research caches cleared at run completion. No module-level shared cache.
- SOUL.md not injected into prompts for a different firm's matters.

---

## 17. Target Folder Structure

```
themis/
  agents/
    definitions.py       ← agent_definitions dict (Lavern pattern)
    profiles.py          ← agent_profiles dict
    tool_arrays.py       ← shared tool array constants
    senior_counsel.py    ← Senior Counsel subgraph
    researcher.py        ← ResearcherAgent subgraph
    drafter.py           ← DrafterAgent subgraph
    reviewer.py          ← ReviewerAgent subgraph
    verification.py      ← VerificationAgent subgraph
    prompts/
  db/
    models.py            ← SQLAlchemy Matter, Firm, Lawyer
    matter_store.py      ← get/create/update/persist_matter
    migrations/
      001_matters.py     ← Alembic + RLS policy
  worker/
    main.py              ← ARQ worker entrypoint
    jobs.py              ← run_matter_job, index_matter_job, recover_paused_matters
  mcp/
    debate_server.py     ← mcp__lex__ debate board MCP server
  workspace/
    models.py            ← Pydantic workspace objects
    repository.py        ← typed queries
    projections.py
    mutations.py
  runtime/
    events.py
    event_bus.py
    planner.py
    executor.py
    approvals.py
  ingestion/
    documents.py
    ocr.py
    extractors.py
    chronology.py
    evidence.py
  learning/
    feedback.py
    preferences.py
    playbooks.py
  memory/
    os.py
    working.py
    matter.py
    episodic.py
    semantic.py
    firm.py
    lawyer.py
  knowledge/
    sources/
    graph.py
    vector.py
    citations.py
  tools/
    kanoon_api.py        ← httpx REST client (R1)
    tavily_search.py     ← Tavily integration (R1)
    browser_verification.py  ← browser-use + Stagehand + Skyvern (R1)
    redline.py           ← OOXML tracked-changes (doc-haus bridge)
  nodes/
    chamber.py           ← adversarial review MVP (doc-haus bridge)
    grid.py              ← cross-document grid analysis (doc-haus bridge)
  skills/
    loader.py
    registry.py
    packages/
  gateway/
    control_plane.py
    adapters/
  security/
  ui/
    terminal/
```

---

## 18. Build Sequence

### Numbering System

The V3.x labels are **implementation build steps** (from grilling session). They map to phases in the old roadmap as follows:

| Build step | What | Old roadmap equivalent |
|---|---|---|
| V3.1 | Matter Model | Phase 2 (Canonical Matter Workspace) |
| V3.2 | State Split | Prerequisite for Phase 11 |
| V3.3 | Multi-Agent Graph + Debate MCP | Phase 11 MVP |
| V3.4 | ARQ + Redis Worker | Phase 3 (Living Agent MVP) |
| R1 | ReAct ResearcherAgent | Phase 10 (Investigation Research Agent) |
| R2A/B | mem0 Memory Layer | Phase 8 (LexMemory OS) |
| R2C | KB File Upload | Phase 4 (Bulk Document Intelligence) |
| R3 | Parallel Agents + LLM Council | Phase 7 (Dynamic Planner) |
| R4 | Filing Bundle Generator | Phase 13 (Legal Skill OS) |
| R5 | Skill Creator + Translation | Phase 13 (Legal Skill OS) |
| R7 | JARVIS Router + Control Plane JWT | Phase 14 (Gateway Completion) |
| R8 | Security + DPDP Compliance | Phase 16 (Enterprise Hardening) |

---

### V3.1 — Matter Model *(anchor — everything references matter_id)*

**New files:**
- `themis/db/models.py` — SQLAlchemy `Matter`, `Firm`, `Lawyer` models
- `themis/db/migrations/001_matters.py` — Alembic migration + RLS policy
- `themis/db/matter_store.py` — `get_matter()`, `create_matter()`, `update_matter()`, `persist_matter()`

**Gate:** `pytest tests/test_matter_store.py` — CRUD + RLS isolation passing

---

### V3.2 — State Split *(unblocks graph work)*

**Changed files:**
- `themis/state.py` — `LexState` → `SeniorCounselState` + 4 child TypedDicts
- Every file in `themis/nodes/` — update field references
- All test files — update state construction

**Gate:** `pytest tests/` — all existing tests still passing (~279 tests green)

---

### V3.3 — Multi-Agent Graph Restructure *(the core pivot)*

**New files:**
- `themis/agents/definitions.py`
- `themis/agents/profiles.py`
- `themis/agents/tool_arrays.py`
- `themis/agents/senior_counsel.py`
- `themis/agents/researcher.py` — stub, ReAct loop comes in R1
- `themis/agents/drafter.py`
- `themis/agents/reviewer.py`
- `themis/agents/verification.py`
- `themis/mcp/debate_server.py`

**Changed files:**
- `themis/graph.py` — Senior Counsel graph wiring, `send()` dispatch, `persist_matter()` hooks

**Gate:** `lex draft "test NI Act matter"` passes end-to-end. `pytest tests/` green.

---

### V3.4 — ARQ + Redis Worker *(living agent)*

**New files:**
- `themis/worker/main.py` — ARQ worker entrypoint
- `themis/worker/jobs.py` — `run_matter_job()`, `index_matter_job()`, `recover_paused_matters()`

**Changed files:**
- `docker-compose.yml` — add `lexagent-worker`, `mcp-lex-debate`, `redis`, `qdrant` services
- `themis/memory/session_store.py` — before V3.4 ships, `add_reminder()`, `list_reminders()`, `get_due_reminders()`, and `delete_reminder()` must scope by `telegram_user_id` (add a non-null constraint and filter on it). The current implementation stores `telegram_user_id` but never filters on it, causing cross-user reminder leakage in multi-user Telegram deployments. V3.4 replaces this system with domain events, but the SQLite path must be patched for the interim.

**Gate:** Worker starts, picks up paused matter from Postgres, runs graph, writes back. `pytest tests/test_worker.py` green.

---

### R1 — ReAct ResearcherAgent *(first feature on V3 foundation)*

**New files:**
- `themis/tools/kanoon_api.py` — httpx REST client for Indian Kanoon
- `themis/tools/tavily_search.py` — Tavily web search
- `themis/tools/browser_verification.py` — browser-use + Stagehand + Skyvern + Bright Data MCP

**Changed files:**
- `themis/agents/researcher.py` — replace stub with full ReAct loop (`plan → search → fetch → evaluate → loop`), citation gate (drops findings without `{title, citation, doc_excerpt, url}`), Qdrant sync indexing

**Gate:** `pytest tests/test_react_research.py` — citation gate + LLM routing + Qdrant sync passing.

---

### R2A/R2B — mem0 Memory Layer

**New files:**
- `themis/memory/mem0_client.py` — wraps `mem0ai.Memory` with Qdrant backend
- `themis/memory/lawyer_memory.py` — `load_lawyer_profile()`, `save_feedback()`, `load_matter_context()`

**Changed files:**
- `themis/memory/soul.py` — route reads/writes through `lawyer_memory.py`, file fallback when mem0 disabled
- `themis/nodes/draft.py` — read lawyer profile from mem0, persist on completion

**Gate:** `pytest tests/test_mem0_client.py` green.

---

### R2C — KB File Upload + Ingestion Pipeline

**New files:**
- `themis/kb/ingestion.py` — PDF/DOCX/image/CSV → LlamaParse/pandas → chunks → Qdrant
- `themis/kb/collections.py` — centralised Qdrant collection naming (`firm`, `matter`, `judgments`)
- Control plane endpoint: `POST /api/v1/kb/upload`

**Gate:** `pytest tests/test_kb_ingestion.py` green.

---

### R3 — Parallel Agents + LLM Council

**New files:**
- `themis/nodes/parallel_orchestrator.py` — Mode 1 (JARVIS auto-split), Mode 2 (`/parallel`), Mode 3 (adversarial debate, 2/3 convergence)

**Changed files:**
- `themis/graph.py` — add `parallel_research` node + conditional edges

---

### R4 — Filing Bundle Generator

**New files:**
- `themis/nodes/bundle_generator.py`
- `themis/skills/bundle_templates/ni_act_138.yaml` — 9-slot NI Act S.138 template (4 agent-drafted + 5 lawyer-uploaded)

---

### R5 — Skill Creator + Translation Node

**New files:**
- `themis/nodes/skill_creator.py`
- `themis/nodes/translator.py` — reading mode (LLM) + filing mode (terminology preservation)
- `themis/connectors/mcp_connector.py`, `rest_connector.py`, `connector_store.py`

---

### R7 — JARVIS Intent Router + Control Plane JWT

**New files:**
- `themis/nodes/jarvis_router.py` — 12-intent classifier
- `themis/gateway/intent_router.py`

**Changed files:**
- `themis/gateway/control_plane.py` — JWT auth, rate limiting (slowapi), audit logging
- `themis/gateway/telegram.py` — bind Telegram `user_id` to `lawyer_id` at session start; `_resume_matter` and `_try_load_matter` must verify that the requesting Telegram user owns the matter before loading state (query `matters.lawyer_id` via the workspace repo with `app.firm_id` set — RLS alone does not prevent cross-user access within the same firm)

**Known gap closed here:** Postgres RLS (V3.1) prevents cross-firm matter access but does not prevent one lawyer within a firm from loading a colleague's matter via a guessed matter ID. The ownership check in the Telegram gateway closes this.

---

### R8 — Security + DPDP Compliance

**New files:**
- `themis/security/encryption.py` — AES-256-GCM for Qdrant payload fields
- `themis/security/audit.py` — structlog DPDP audit logger
- `themis/security/jwt_auth.py` — JWT replacing naive bearer token

---

## 19. doc-haus Bridge Features

*Three capabilities ported from [sure-scale/doc-haus](https://github.com/sure-scale/doc-haus). Ship before V3 because they are independent of the matter workspace infra.*

### Feature 1: Tracked-Changes Redlining (`themis/tools/redline.py`)

OOXML `<w:ins>`/`<w:del>` via lxml, paragraph-level difflib. No new tables, no draft versioning infra required. Ships as a tool; review node calls it if `redline_source_path` is set in state.

**State fields:** `redline_source_path: Optional[str]`, `redline_output_path: Optional[str]`
**CLI:** `lex draft "..." --redline /tmp/original.docx`

### Feature 2: Adversarial Chamber MVP (`themis/nodes/chamber.py`)

Three sequential LLM calls: Reviewer → Challenger → Summarizer. Phase 11 replaces the node internals; external interface stays identical.

**State fields:** `chamber_enabled: bool`, `chamber_issues`, `chamber_pushback`, `chamber_review`
**CLI:** `lex draft "..." --chamber`
**Graph:** conditional edge `draft → chamber → review`

### Feature 3: Grid Analysis (`themis/nodes/grid.py`)

Runs a fixed question list across every document in the matter workspace in parallel: `{question: {doc_name: answer}}`. `_list_matter_docs` will be swapped for a workspace repository query when Phase 4 ingestion ships.

**State fields:** `grid_questions: list[str]`, `grid_results: dict`
**CLI:** `lex grid <matter_id> --questions "Q1" "Q2" --csv output.csv`

---

## 20. Docker Compose

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: lexagent
      POSTGRES_USER: lex
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [postgres_data:/var/lib/postgresql/data]

  qdrant:
    image: qdrant/qdrant:latest
    volumes: [qdrant_data:/qdrant/storage]
    ports: ["6333:6333"]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]

  lexagent-control-plane:
    build: .
    command: uvicorn themis.gateway.control_plane:app --host 0.0.0.0 --port 8000
    depends_on: [postgres, qdrant, redis]
    env_file: .env

  lexagent-worker:
    build: .
    command: python -m themis.worker.main
    depends_on: [postgres, qdrant, redis]
    env_file: .env

  mcp-lex-debate:
    build: .
    command: python -m themis.mcp.debate_server
    depends_on: [postgres]
    env_file: .env

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

---

## 21. New Dependencies (pyproject.toml additions)

```toml
arq = ">=0.26"
redis = ">=5.0"
sqlalchemy = {extras = ["asyncio"], version = ">=2.0"}
alembic = ">=1.13"
browser-use = ">=0.1"
stagehand-py = ">=0.1"
skyvern = ">=0.1"
mem0ai = ">=0.1.29"          # R2B
tavily-python = ">=0.3.0"    # R1
llama-parse = ">=0.4.0"      # R2C
python-jose = {extras=["cryptography"], version=">=3.3.0"}  # R8
structlog = ">=24.0"          # R8
slowapi = ">=0.1.9"           # R7
pandas = ">=2.2"              # R2C
mcp = ">=1.0.0"               # debate server
langchain-mcp-adapters = ">=0.1.0"
```

---

## 22. Key Invariants (Never Violate)

1. **Only Senior Counsel calls `persist_matter()`** — specialists never write to Postgres directly.
2. **Only Senior Counsel reads/writes mem0** — specialists receive memory as typed input fields.
3. **`next_action` is always structured JSON** — never free text. ARQ must deserialise and invoke without an LLM step.
4. **Every query to `matters` sets `app.firm_id` first** — RLS, no exceptions, no full-table scans.
5. **Every agent has `decline_to_find`** — confidence < 0.5 triggers human review, not a hallucinated finding.
6. **Judgments indexed to Qdrant synchronously** — DrafterAgent needs them in the same run. Matter summaries/feedback indexed async.
7. **Whitelist validation on every LLM-generated plan** — planner cannot invent a specialist not in `SPECIALIST_WHITELIST`.
8. **`thread_messages` per specialist, clean narrative in parent `messages`** — specialists log internally, Senior Counsel narrates to lawyer.
9. **Matter context ≠ session context** — `SeniorCounselState` is ephemeral run context; Workspace tables are permanent.
10. **In-process research caches must be scoped to `thread_id`/`matter_id`** and cleared at run end. No module-level shared cache.

---

## 23. What to Keep, Remove, and Postpone

### Keep
- LangGraph as execution substrate
- Control plane
- Thin gateway pattern
- Skills, upgraded to manifests
- AES-256-GCM + HKDF (not Fernet)
- Postgres checkpointer, as run state only
- Postgres jobs/events for the living agent MVP
- Citation enforcement gate
- Explicit learning loop from feedback, edits, accepted authorities, rejected outputs
- Qdrant retrieval with legal corpus partitioning
- Terminal UI vision as a runtime client
- Contract review/playbooks
- Voice gateway as optional adapter

### Remove
- Claims that static token auth is enterprise auth
- CORS wildcard in any enterprise path
- Duplicate security module names (`jwt_auth.py` vs `tokens.py`, `encryption.py` vs `crypto.py`)
- `LexState` as a flat catch-all TypedDict with 60+ fields
- File markdown memory as authoritative legal state
- Any self-learning mechanism that silently rewrites prompts, skills, or playbooks
- Any living-agent behavior that sends, files, or communicates externally without approval

### Postpone
- Full 67-agent roster
- LlamaParse as default ingestion; use `pdfplumber` + OCR fallback first
- PageIndex until long-document retrieval is a measured bottleneck
- OpenAPI/MCP arbitrary connector marketplace
- LLM council across providers
- Translation filing mode
- Email sending automation beyond approval-gated drafts
- Paid SCC/Lexis/Westlaw integrations until licensing is clear

---

## 24. Privacy Control Architecture (lq.ai Pattern)

**Problem:** Cloud LLMs (Claude, GPT, Gemini), external search APIs (Tavily, Indian Kanoon), and third-party tools receive raw matter data today. A single API call can expose client names, amounts, case strategies, and Indian PII (Aadhaar, PAN) to cloud providers whose data retention policies are outside the firm's control. This violates attorney-client privilege, DPDP Act 2023, and basic legal ethics.

**Solution — the lq.ai separation principle:** Cloud LLMs need the *structure* of a legal document (argument patterns, clause logic, legal reasoning) but not the *facts* (party names, amounts, dates, identifiers). Redact facts before the cloud boundary, send structure, restore facts after. The cloud never sees real client data.

---

### 24.1 Privacy Modes

Controlled via `LexConfig.privacy_mode`:

| Mode | Who uses it | Behaviour |
|---|---|---|
| `PRIVACY_OFF` | Personal/dev mode | No redaction. All data flows to cloud as-is. |
| `PRIVACY_REDACT` | Enterprise default | Redact → cloud → restore. Client data never leaves perimeter in plaintext. |
| `PRIVACY_LOCAL_ONLY` | Maximum security | No cloud LLM calls. All inference via local models (Ollama, vLLM). Redaction still applies to external search APIs. |

---

### 24.2 What Gets Redacted Per API Type

Not all external APIs carry the same risk. Policy is per-destination:

| External API | Redaction policy | Reason |
|---|---|---|
| Cloud LLMs (Claude, GPT, Gemini) | Full PII + legal entity redaction | Inference provider; highest risk of data training/retention |
| Tavily web search | Query-level redaction — no party names or case numbers in search queries | Queries are logged by third party |
| Indian Kanoon | No redaction for document retrieval (public data). Redact matter context injected into search queries | Read-only public corpus; search query may contain matter facts |
| eCourts | Case number only in queries. Never embed party facts in API params | Public court system; case numbers already public |
| Bright Data MCP | Redact before any structured extraction prompt | Cloud scraping proxy; prompt content is transmitted |
| mem0 cloud | Full redaction before storing memories | Cloud memory provider; highest retention risk |
| Qdrant (self-hosted) | No redaction — within perimeter | Local infra; RLS + encryption at rest sufficient |
| Qdrant (cloud) | Redact before indexing; vault entries needed for restoration on retrieval | Cloud vector DB; embeddings can leak entity information |

---

### 24.3 Entity Categories and Placeholder Format

Placeholders are **deterministic within a matter** — same entity always maps to the same placeholder across all LLM calls in the same matter run. This keeps LLM output coherent (the model sees consistent `[PARTY_A]` references and reasons correctly about them).

Placeholder format: `[CATEGORY_HASH]` where hash = `sha256(matter_id + entity_text)[:6]`

| Category | Example real value | Placeholder |
|---|---|---|
| `PARTY_COMPLAINANT` | Ankush Sareen | `[PARTY_COMPLAINANT_A3F2C1]` |
| `PARTY_ACCUSED` | XYZ Pvt Ltd | `[PARTY_ACCUSED_B7D4E2]` |
| `PARTY_COUNSEL` | Adv. Sharma | `[PARTY_COUNSEL_C1A9F3]` |
| `PARTY_BANK` | HDFC Bank, Connaught Place | `[PARTY_BANK_D5B2A1]` |
| `AMOUNT` | Rs. 5,00,000 | `[AMOUNT_E8C3F4]` |
| `CHEQUE_NUMBER` | 004521 | `[CHEQUE_F2A1B9]` |
| `ACCOUNT_NUMBER` | 1234567890 | `[ACCOUNT_G3D5C2]` |
| `ADDRESS` | 42, Sector 14, Gurugram | `[ADDRESS_H6E1D4]` |
| `PHONE` | +91 98765 43210 | `[PHONE_I4F7A3]` |
| `EMAIL` | client@example.com | `[EMAIL_J2B8C5]` |
| `AADHAAR` | 1234 5678 9012 | `[ID_AADHAAR_K9A2E1]` |
| `PAN` | ABCDE1234F | `[ID_PAN_L1C6B3]` |
| `CASE_NUMBER` | CC/1234/2024 | `[CASE_M5D3A7]` |
| `DATE_SENSITIVE` | 10 January 2025 | `[DATE_N7F2C4]` (only for sensitive operative dates) |
| `JUDGE_NAME` | Hon. Sri R.K. Sharma | `[JUDGE_O3A8B2]` |

---

### 24.4 Architecture Components

```
themis/privacy/
├── redactor.py        ← detects + replaces entities; returns (redacted_text, vault_entries)
├── entity_vault.py    ← Postgres-backed encrypted store: placeholder → real value
├── restorer.py        ← inverse mapping; applied to every cloud response before storage
├── policy.py          ← per-API-destination redaction policy
├── audit.py           ← logs what entity categories were sent to which API (not the values)
└── cloud_boundary.py  ← middleware wrapper; all external calls pass through this
```

#### `redactor.py`

Uses **spaCy** (local NER, runs on-device) + **Microsoft Presidio** (PII detection, runs locally) + a custom Indian legal entity pattern layer on top. No cloud model involved in redaction — that would be a circular dependency.

```python
# themis/privacy/redactor.py

class Redactor:
    """
    Detects and replaces PII and legal entities in text before cloud API calls.
    Runs entirely locally — spaCy + Presidio + Indian legal regex patterns.
    Returns (redacted_text, list[VaultEntry]) where VaultEntry maps placeholder → real value.
    """

    def redact(self, text: str, matter_id: str, policy: RedactionPolicy) -> RedactionResult:
        """
        Args:
            text:       Plaintext to redact (prompt, context, query).
            matter_id:  Scopes placeholder determinism to this matter.
            policy:     Which entity categories to redact for this destination.

        Returns:
            RedactionResult(redacted_text, vault_entries, entity_count_by_category)
        """
        ...

    def _deterministic_placeholder(self, matter_id: str, entity_text: str, category: str) -> str:
        h = hashlib.sha256(f"{matter_id}:{entity_text}".encode()).hexdigest()[:6].upper()
        return f"[{category}_{h}]"
```

**Detection stack (in order):**
1. Presidio `AnalyzerEngine` — PHONE, EMAIL, AADHAAR, PAN, CREDIT_CARD, IBAN
2. spaCy `en_core_web_lg` NER — PERSON, ORG, GPE, MONEY, DATE
3. Indian legal regex patterns — case numbers (`CC/\d+/\d{4}`), cheque numbers, account numbers, court names
4. Matter-aware override — entities already in the matter's `parties` JSONB are always redacted regardless of NER confidence

#### `entity_vault.py`

```python
# themis/privacy/entity_vault.py

# Postgres schema:
# CREATE TABLE entity_vault (
#     vault_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     firm_id      UUID NOT NULL REFERENCES firms(firm_id),
#     matter_id    UUID NOT NULL REFERENCES matters(matter_id),
#     placeholder  TEXT NOT NULL,
#     real_value   BYTEA NOT NULL,   -- AES-256-GCM encrypted with firm key
#     category     TEXT NOT NULL,
#     created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
#     UNIQUE (matter_id, placeholder)
# );
# ALTER TABLE entity_vault ENABLE ROW LEVEL SECURITY;
# CREATE POLICY firm_isolation ON entity_vault USING (firm_id = current_setting('app.firm_id')::UUID);

class EntityVault:
    async def store(self, matter_id: str, firm_id: str, entries: list[VaultEntry]) -> None: ...
    async def restore(self, matter_id: str, text: str) -> str: ...
    async def purge(self, matter_id: str) -> None: ...  # DPDP erasure
    async def export(self, matter_id: str) -> list[VaultEntry]: ...  # DPDP portability
```

Real values are encrypted with the firm's AES-256-GCM key (via existing `themis/security/crypto.py`) before storage. Decryption only happens during restoration, in-process, never logged.

#### `cloud_boundary.py`

This is the enforcement point. Every external call passes through it. Nodes **never call external APIs directly**.

```python
# themis/privacy/cloud_boundary.py

class CloudBoundary:
    """
    Sits between agent nodes and all external APIs.
    In PRIVACY_REDACT mode: redact → call → restore.
    In PRIVACY_OFF mode: passthrough.
    In PRIVACY_LOCAL_ONLY mode: blocks cloud LLM calls; allows read-only public APIs.
    """

    async def call_llm(
        self,
        messages: list[dict],
        matter_id: str,
        firm_id: str,
        destination: str = "cloud_llm",
    ) -> str:
        if self.mode == PrivacyMode.PRIVACY_OFF:
            return await self._raw_llm_call(messages)

        policy = self.policy_engine.get_policy(destination)
        redacted_messages, vault_entries = self.redactor.redact_messages(messages, matter_id, policy)
        await self.vault.store(matter_id, firm_id, vault_entries)
        await self.audit.log(destination, matter_id, firm_id, vault_entries)

        raw_response = await self._raw_llm_call(redacted_messages)

        restored = await self.vault.restore(matter_id, raw_response)
        return restored

    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        matter_id: str,
        firm_id: str,
    ) -> dict:
        destination = self.policy_engine.tool_destination(tool_name)
        policy = self.policy_engine.get_policy(destination)
        redacted_params, vault_entries = self.redactor.redact_dict(params, matter_id, policy)
        await self.vault.store(matter_id, firm_id, vault_entries)
        await self.audit.log(destination, matter_id, firm_id, vault_entries)

        raw_result = await self._raw_tool_call(tool_name, redacted_params)

        restored = await self.vault.restore(matter_id, str(raw_result))
        return restored
```

#### `audit.py`

Logs **categories of entities redacted**, not the values or placeholders. The audit trail answers "what kind of data went to which API" for compliance reporting without itself being a data leak.

```python
# audit log entry shape
{
    "timestamp":           "2026-06-23T10:15:30Z",
    "api_destination":     "cloud_llm:claude-opus-4-8",
    "firm_id":             "firm_abc",           # hashed in log
    "matter_id":           "matter_xyz",          # hashed in log
    "entities_redacted":   ["PARTY_COMPLAINANT", "AMOUNT", "CHEQUE_NUMBER"],
    "entity_count":        3,
    "call_id":             "uuid"                 # links to LangGraph run
    # real values: NEVER logged
    # placeholders: NEVER logged
}
```

---

### 24.5 Integration Points in the Agent Graph

The `CloudBoundary` is injected into Senior Counsel at graph construction time and passed to every specialist via `LexConfig`. Specialists call `config.cloud_boundary.call_llm()`, never `anthropic.messages.create()` directly.

```
SeniorCounselState.matter_id + firm_id
        ↓
ResearcherAgent.run(state)
        ↓
cloud_boundary.call_llm(messages, matter_id, firm_id)
        ↓
Redactor → Entity Vault → Claude API → Restorer
        ↓
Restored response (real names/values back in)
        ↓
research_findings stored in Postgres with real values
```

**Key invariant:** Redaction is a cloud boundary concern, not a node concern. Nodes work with real data internally. The boundary enforces privacy at the moment of egress.

---

### 24.6 What Goes Through Redaction vs What Stays Local

```
WITHIN PERIMETER (no redaction needed)
  Postgres queries (RLS enforces isolation)
  Qdrant self-hosted (within docker-compose network)
  LangGraph checkpointer (Postgres)
  Entity Vault reads/writes
  File reads from ~/.themis/
  Draft assembly (docx_writer.py)
  SOUL.md / MEMORY.md reads

CROSSES CLOUD BOUNDARY (redaction enforced)
  call_llm() → any cloud model
  kanoon_api.py → Indian Kanoon search queries
  tavily_search.py → Tavily queries
  browser_verification.py → browser-use / Stagehand prompts
  brightdata_fetch() → Bright Data MCP
  mem0 cloud API (if not self-hosted)
  Qdrant cloud API (if not self-hosted)
```

---

### 24.7 DPDP Act 2023 Compliance Hooks

The Digital Personal Data Protection Act 2023 applies to personal data of Indian data subjects. The vault design satisfies the key obligations:

| Obligation | Implementation |
|---|---|
| **Data minimisation** | Redaction sends only what's needed for the task; vault entries only created when entity actually appears in a cloud-bound call |
| **Purpose limitation** | `audit.py` records destination + purpose; vault entries tagged with `created_for` (e.g. `"research_query"`) |
| **Storage limitation** | `entity_vault.purge(matter_id)` called on matter close or lawyer erasure request |
| **Right to erasure** | `purge()` deletes all vault entries for a matter. Cloud provider already received redacted text — real values were never sent |
| **Data portability** | `entity_vault.export(matter_id)` returns all vault entries in structured format |
| **Breach notification** | Audit log is the evidence record; vault entries are encrypted so a DB breach does not expose real values |
| **Data localisation** | Self-hosted Postgres + Qdrant + Redis within India-region infra. Cloud LLMs receive only redacted (de-identified) text |

---

### 24.8 Build Step: R9 — Privacy Control Layer

Sits after R8 (Security + DPDP) in the build sequence.

**New files:**
- `themis/privacy/redactor.py` — spaCy + Presidio + Indian legal patterns
- `themis/privacy/entity_vault.py` — encrypted Postgres vault store
- `themis/privacy/restorer.py` — inverse mapping after cloud response
- `themis/privacy/policy.py` — per-destination redaction policy
- `themis/privacy/audit.py` — entity category audit logger
- `themis/privacy/cloud_boundary.py` — enforcement middleware
- `themis/db/migrations/004_entity_vault.py` — Alembic migration + RLS policy

**Changed files:**
- `themis/config.py` — add `privacy_mode: PrivacyMode`, `cloud_boundary: CloudBoundary`
- `themis/nodes/_llm.py` — replace direct `call_llm()` with `cloud_boundary.call_llm()`
- Every tool in `themis/tools/` that calls an external API — route through `cloud_boundary.call_tool()`
- `pyproject.toml` — add `spacy>=3.7`, `presidio-analyzer>=2.2`, `presidio-anonymizer>=2.2`

**New deps:**
```toml
spacy = ">=3.7"
presidio-analyzer = ">=2.2"
presidio-anonymizer = ">=2.2"
# en_core_web_lg downloaded separately: python -m spacy download en_core_web_lg
```

**Gate:**
```bash
pytest tests/test_redactor.py      # entity detection, deterministic placeholders
pytest tests/test_entity_vault.py  # store, restore, purge, RLS isolation
pytest tests/test_cloud_boundary.py # redact→call→restore round-trip (mocked API)
pytest tests/test_privacy_audit.py  # audit log shape, no real values logged

# Integration test:
# Create matter with party "Ankush Sareen" + amount "Rs. 5,00,000"
# Run research node in PRIVACY_REDACT mode
# Assert: Claude API was called with "[PARTY_COMPLAINANT_A3F2C1]" not "Ankush Sareen"
# Assert: research_findings in Postgres contain "Ankush Sareen" (restored)
# Assert: audit log contains category "PARTY_COMPLAINANT" not name
pytest tests/test_privacy_integration.py
```

---

### 24.9 Key Invariants for Privacy Layer

1. **Redactor never calls a cloud model** — spaCy + Presidio run locally only. Circular dependency is a data breach.
2. **Real values never persist in redacted form** — restoration happens before any storage call. Placeholders are ephemeral transport tokens.
3. **Entity Vault is scoped per `(firm_id, matter_id)`** — vault entries from one matter cannot be used to restore another matter's LLM responses.
4. **Audit log records categories, never values or placeholders** — the log is safe to export for compliance review.
5. **`PRIVACY_OFF` is only valid when `personal_mode=True`** — enterprise mode cannot disable redaction. `LexConfig` enforces this.
6. **Vault entries are encrypted with the firm's key** — a Postgres breach exposes ciphertext, not client names.
7. **`purge()` is irreversible** — after erasure, vault entries are gone. The cloud already received only redacted text, so erasure is complete.
8. **Indian Kanoon + eCourts queries contain no matter-specific facts** — search queries use only legal concepts (e.g. `"dishonour of cheque limitation period"` not `"Ankush Sareen vs XYZ Ltd"`).
9. **`PRIVACY_LOCAL_ONLY` blocks all cloud LLM calls** — `cloud_boundary.call_llm()` raises `PrivacyPolicyViolation` if destination is a cloud model in this mode. Tools must use local models.
