# LexAgent OS V3 Architecture Roadmap

Status: architectural synthesis, not implementation.
Date: 2026-05-30.
Authoritative inputs reconciled: `CLAUDE.md`, `Enterprise_10x10_Plan.md`, `openclaw_legal_assistant_plan.md`, `POST_PHASE8B_IMPLEMENTATION_PLAN.md`, `Security_features.md`, `UI-terminal.md`, `REVAMP_PLAN.md`, plus live code inspection.

## 0. Brutally Honest Answer

### What LexAgent Is Today

LexAgent is a LangGraph-based Indian legal workflow agent with a solid teaching-build foundation. It can intake a brief, run a mostly linear research path, draft, verify citations, review, persist some memory, expose a FastAPI control plane, support Telegram/voice gateway pieces, run contract review, store sessions in SQLite, optionally checkpoint LangGraph state in Postgres, and optionally index retrieval material in Qdrant.

It is more than a toy. It has real primitives: `LexState`, `StateGraph`, node contracts, tool registry, skills, lawyer/matter memory, control plane, voice gateway, research APIs, citation gate, security package scaffolding, tests, and config discipline.

### What LexAgent Is Pretending To Be

LexAgent currently presents itself as if it is already a persistent agent platform. It is not. The control plane still uses a static bearer secret rather than the security package. Multi-tenant config exists, but SQLite session/reminder isolation is not enforced. Memory remains mostly file/session based. The graph is still workflow-centric and mostly static. The "ReAct research" node is API-first and gated, but not yet an actual autonomous investigation loop with hypothesis/refinement. The scheduler is reminder-specific, not a general proactive runtime. The matter model is implicit in `LexState`, markdown logs, snapshots, and checkpoint state rather than a first-class legal workspace.

### What LexAgent Must Become

LexAgent must become a persistent legal operating system centered on a matter workspace, not a chat session. The core product should be:

1. A durable legal matter state model.
2. A 24/7 living agent that keeps working on matters while the lawyer is offline.
3. Bulk document intelligence for PDFs, images, scanned copies, emails, and knowledge-base files.
4. A dynamic planner that creates execution DAGs per goal.
5. A legal runtime that schedules, resumes, audits, and supervises long-running work.
6. A learning loop that improves drafting, research, compliance checks, and skills from lawyer feedback.
7. A legal memory OS with separate working, matter, episodic, semantic, procedural, firm, and lawyer memories.
8. Specialist legal subagents coordinated by a Senior Counsel agent, with verification gates before output leaves the system.
9. Thin gateways and a rich terminal/web legal IDE that view and control the same runtime.

The platform should not become a Harvey clone, generic chatbot, or pile of "AI features". The wedge is a living matter workspace: LexAgent should wake up before the lawyer, process the matter file, build the chronology, draft next documents, identify risks, prepare research memos, and say what needs to be done next.

## 1. Current Architecture Audit

### Current State Diagram

```text
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
intake
  | incomplete -> END, caller asks user and resumes
  | contract_review -> contract_review -> END
  | no-research matter -> draft
  v
research / react_research
  |
  | Kanoon stub/API/Playwright, Tavily optional, limitation tool
  v
draft
  |
  | auto_verify_citations + findings?
  v
cite
  |
  v
review
  |
  v
Outputs: draft, summary, docx, risk notes, citation status
  |
  v
Persistence
  - LangGraph MemorySaver or AsyncPostgresSaver
  - SQLite sessions.db + reminders + chat_messages
  - ~/.lexagent/SOUL.md
  - ~/.lexagent/matters/{matter_id}/MEMORY.md + state.json
  - optional Qdrant collections
  - judgment cache under ~/.lexagent/judgments
```

### Live Components

Graph:
- `lexagent/graph.py` defines a static LangGraph with `intake`, `research`, `draft`, `cite`, `review`, `contract_review`.
- Postgres checkpointing exists behind `postgres_url`; otherwise MemorySaver.
- Routing is condition-based but not planner-generated.

State:
- `lexagent/state.py` is a large `TypedDict`.
- It mixes matter facts, transient workflow flags, gateway identity, voice state, research traces, and output artifacts.
- This is workable for a teaching graph but too loose for a legal OS.

Memory:
- Lawyer memory: `SOUL.md`.
- Matter memory: append-only `MEMORY.md` plus `state.json`.
- Session memory: SQLite `sessions`, `chat_messages`.
- Checkpoint memory: LangGraph checkpointer.
- Missing: typed matter workspace, semantic/procedural/firm memory with governance.

Tools:
- Tool registry exists and supports decorated tools.
- Kanoon API/fallback, retriever, reranker, query expansion, RAPTOR, legal KG, limitation, docx, court fees, contract playbooks exist.
- Missing: tool capability model, approval policy, per-tenant tool namespaces, tool traces as first-class audit objects.

Gateways:
- Control plane exists.
- Telegram, voice, setup wizard/integrations exist.
- Control plane still carries dev CORS wildcard and static token auth.
- Thin-adapter goal is partially implemented but not complete.

Storage:
- SQLite for sessions/reminders/chat.
- File system for matter/lawyer memory.
- Postgres optional for LangGraph checkpoints.
- Qdrant optional for retrieval.
- No canonical matter database schema.

Research:
- Legacy research plus API-first `react_research`.
- Citation enforcement gate exists.
- It is not yet a full investigation agent: no explicit hypothesis loop, source comparison matrix, negative authority search, or court-level treatment analysis.

Drafting and verification:
- Draft, cite, review nodes exist.
- Citation verification exists, but verification is still a node in a workflow, not a multi-pass quality system with risk/procedure/senior counsel review.

### Bottlenecks

1. Workflow-centric design: the graph encodes document generation, not legal operations.
2. Static graph: adding new workflows bloats conditional edges and `LexState`.
3. No planner: the system cannot decide that a writ, arbitration, NI Act complaint, and contract review need different DAGs.
4. Weak runtime: no job model, event bus, run lifecycle, pause/resume/approval model, or durable task queue.
5. No living agent: the system does not keep working overnight or proactively prepare the next matter.
6. No bulk document intelligence: 50+ PDFs/images/scanned documents cannot become a chronology, fact sheet, evidence table, and research brief automatically.
7. Weak memory boundaries: file memory, session memory, and checkpoint memory overlap without a typed matter source of truth.
8. No explicit learning loop: lawyer edits, accepted authorities, rejected arguments, and repeated workflows are not turned into reusable improvement.
9. Tool orchestration is shallow: tools are called by nodes, not selected under a policy/skill/runtime framework.
10. Security scaffolding not wired: packages exist but control plane/session store do not enforce the enterprise plan.
11. Research is retrieval-heavy: it searches and fetches; it does not yet investigate.
12. Verification is underpowered: citation gate prevents the worst errors but does not guarantee legal validity.
13. Terminal vision is not connected to runtime data models.

## 2. OpenClaw Gap Analysis

| Dimension | Score | Assessment |
|---|---:|---|
| Runtime | 3/10 | LangGraph checkpoints exist, but no agent runtime with job lifecycle, event loop, cancellation, approvals, retries, or durable queues. |
| Gateway | 5/10 | Control plane and multiple gateway modules exist. Telegram/voice are partially aligned. Needs true thin adapters and central auth. |
| Events | 1/10 | Reminders exist, but no domain event bus or subscription model. |
| Memory | 4/10 | Useful local memory and sessions exist, but no Memory OS or canonical matter memory. |
| Skills | 5/10 | Markdown skill loader is elegant. Needs manifests, workflows, tools, memory, versioning, tests. |
| Subagents | 2/10 | Agent personas exist, but not operational specialist subagents with isolated state and contracts. |
| Agent lifecycle | 2/10 | No run/job state machine. Graph invocation is the lifecycle. |
| Long-running execution | 2/10 | Postgres checkpointing helps, but no background execution runtime. |
| Autonomy | 3/10 | Some auto modes and reminders, but no planner plus event-driven proactive behavior. |

OpenClaw lesson: LexAgent should not copy a consumer assistant. It should adopt the platform pattern: thin gateways, central control plane, event runtime, durable workspace, and inspectable agent state.

## 3. Hermes Five Pillars Gap Analysis

Identity:
- Partially implemented.
- `SOUL.md`, agent personas, `firm_id`, `user_id`, config exist.
- Missing: DB-backed lawyer profile, firm profile, role, bar details, preferences, BYOK, consent and policy records.

Memory:
- Partially implemented.
- Missing layered Memory OS and governance.

Skills:
- Partially implemented.
- Markdown skills exist; no skill manifests, skill-specific tools, workflow DAGs, evals, versioning, or memories.

Tools:
- Partially implemented.
- Registry exists. Needs capability metadata, per-firm enablement, approvals, budget limits, audit traces, connector namespaces.

Crons:
- Partially implemented.
- Hearing reminders exist. Missing living-agent jobs for morning briefs, deadline radar, research queues, document processing, chronology generation, risk analysis, and next-action recommendations.

## 4. MemOS Gap Analysis and LexMemory OS

Current memory is a set of useful persistence hacks, not an operating system.

Target layers:

```text
LexMemory OS
  Working Memory     current run context, DAG node state, scratchpad, active facts
  Matter Memory      canonical matter workspace and lifecycle
  Episodic Memory    conversations, hearings, orders, research sessions, decisions
  Semantic Memory    cases, statutes, principles, issue graph, firm KB
  Procedural Memory  playbooks, skills, filing checklists, court practices
  Firm Memory        institutional templates, preferences, court/judge knowledge
  Lawyer Memory      style, bar profile, preferred arguments, risk tolerance
```

Recommended architecture:
- Postgres: canonical objects, events, tasks, versions, audit, RBAC.
- LangGraph Postgres checkpointer: run-level resumability, not source of truth.
- Qdrant: vector retrieval over documents, judgments, memories, embeddings.
- Knowledge graph: Neo4j, Kuzu, or Postgres `pg_graph`-style tables for legal authority relations.
- Mem0/MemOS concepts: use as a memory extraction and retrieval layer, not as the canonical database.
- Files/object storage: original documents, generated drafts, evidence bundles, encrypted at rest.

Rule: memory extraction may summarize, but canonical legal facts must live as typed matter objects with provenance.

## 5. Legal Chamber Architecture

### Agents

Senior Counsel:
- Owns final answer, delegates, resolves conflicts, enforces verification gates.

Planner Counsel:
- Converts a goal into an execution DAG and required matter objects.

Research Counsel:
- Case law, precedents, treatment, negative authorities.

Statutory Counsel:
- Acts, rules, regulations, notifications, circulars.

Procedure Counsel:
- Jurisdiction, limitation, maintainability, forum, court fees, procedural defects.

Evidence Counsel:
- Documents, chronology, admissions, gaps, exhibit mapping.

Drafting Counsel:
- Pleadings, notices, contracts, affidavits, applications, bundles.

Citation Counsel:
- Verifies citations, source text, page references, treatment history.

Risk Counsel:
- Attacks the draft, finds weak facts, adverse law, procedural objections.

Client Counsel:
- Fact gathering, clarifying questions, client-friendly summaries.

### Interaction Diagram

```text
User Goal
  -> Senior Counsel
    -> Planner Counsel -> Execution DAG
      -> Client Counsel -> missing facts/questions
      -> Evidence Counsel -> timeline/evidence map
      -> Procedure Counsel -> maintainability/limitation/forum
      -> Research Counsel -> cases
      -> Statutory Counsel -> statutes/regulations
      -> Drafting Counsel -> draft artifact
      -> Citation Counsel -> source verification
      -> Risk Counsel -> adversarial critique
      -> Drafting Counsel -> revision
    -> Senior Counsel -> final approval/output
```

## 6. Matter Workspace

Matter Workspace is the product core. It is not chat history and not prompts.

Required objects:
- Matter
- Parties
- Facts
- Issues
- Timeline
- Evidence
- Documents
- Document chunks
- Extracted dates
- Chronology items
- Authorities
- Arguments
- Counterarguments
- Risks
- Deadlines
- Tasks
- Drafts
- Hearings
- Orders
- Research sessions
- Research memos
- Risk analyses
- Morning briefs
- Next actions
- Feedback items
- Style preferences
- Playbook notes

### Pydantic Model Sketch

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
    treatment: Literal["binding", "persuasive", "distinguished", "overruled", "unknown"]
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

Storage:
- Postgres tables for typed objects.
- JSONB only for flexible metadata, not primary legal facts.
- Object storage for files.
- Qdrant vectors linked by object IDs.
- Event log table for all mutations.

Update rules:
- Every mutation emits a domain event.
- Agent-generated facts are `alleged/unknown` until lawyer or document provenance confirms them.
- Deletions are soft delete plus audit.
- Drafts are immutable versions; edits create a new version.
- Authorities cannot become `verified=True` without Citation Counsel pipeline evidence.
- Chronology items extracted from documents must keep document/page/source provenance.
- Learning records are explicit and reviewable; the system must not silently rewrite skills or prompts based on one event.

## 7. Planner Architecture

Current graph is static. Target is a dynamic execution graph:

```text
Goal + Matter Workspace + Policy
  -> Planner Counsel
  -> ExecutionDAG(nodes, dependencies, required_inputs, tools, approval_gates)
  -> Runtime schedules nodes
  -> Agents execute nodes
  -> Events update workspace
```

Examples:

Legal Notice:
```text
intake_facts -> identify_claim -> limitation_check -> draft_notice
-> risk_review -> citation_optional -> final_notice
```

Writ Petition:
```text
intake -> maintainability -> alternative_remedy_analysis -> rights/statute research
-> evidence_timeline -> grounds -> prayer -> draft_petition
-> procedure_review -> citation_verification -> risk_attack -> revision
```

Arbitration:
```text
contract_ingest -> arbitration_clause_extract -> seat/venue/law analysis
-> limitation -> notice_invocation_or_section_11_strategy
-> case_research -> draft -> verification
```

NI Act Section 138:
```text
document_checklist -> cheque/date/return_memo/notice/timeline extraction
-> limitation/statutory compliance -> accused/company liability analysis
-> complaint_draft -> evidence_bundle -> verification
```

Contract Review:
```text
contract_ingest -> clause_map -> risk_playbook -> deviation_analysis
-> negotiation_positions -> redline -> executive_summary
```

## 8. Event-Driven Runtime

Events:
- `NEW_DOCUMENT`
- `DOCUMENT_PROCESSED`
- `NEW_FACT`
- `NEW_CHRONOLOGY_ITEM`
- `NEW_HEARING`
- `NEW_PRECEDENT`
- `LIMITATION_WARNING`
- `CLIENT_MESSAGE`
- `EMAIL_RECEIVED`
- `COURT_ORDER`
- `TASK_DUE`
- `DRAFT_APPROVED`
- `AUTHORITY_OVERRULED`
- `FEEDBACK_RECEIVED`
- `MORNING_BRIEF_READY`

Architecture:

```text
Gateway / Cron / Connector / Agent
  -> Event Publisher
  -> Event Bus
  -> Event Store
  -> Subscribers
       - Planner
       - Living Agent Worker
       - Document Processor
       - Chronology Builder
       - Deadline Radar
       - Research Watcher
       - Matter Workspace Projector
       - Notification Dispatcher
       - Audit Logger
       - UI Live Updates
```

Implementation:
- Phase 1: Postgres event table + async in-process dispatcher.
- Phase 2: APScheduler for cron publishers.
- Phase 3: Redis Streams or NATS when multi-process scaling is needed.
- Every event has `event_id`, `firm_id`, `matter_id`, `actor`, `type`, `payload`, `created_at`, `causation_id`, `correlation_id`.

### 8A. 24/7 Living Agent

The living agent is the product behavior that makes LexAgent feel like an operating system instead of a chatbot. It works when the lawyer is offline and prepares the matter file before the next work session.

Founder-mode implementation:
- Use a Postgres `jobs` table.
- Run one `lex worker` process.
- Use APScheduler only for recurring jobs.
- Do not introduce Temporal, Kafka, NATS, or Redis Streams for the MVP.

MVP job types:
- `process_uploaded_documents`
- `extract_facts_and_issues`
- `build_chronology`
- `build_evidence_table`
- `create_research_memo`
- `create_risk_analysis`
- `deadline_scan`
- `morning_brief`
- `next_actions`
- `draft_next_document`

Living Agent flow:

```text
New matter or uploaded files
  -> enqueue process_uploaded_documents
  -> extract text/OCR
  -> chunk documents
  -> extract dates, parties, facts, issues, evidence
  -> build chronology and fact sheet
  -> create research memo and risk memo
  -> identify missing documents/questions
  -> draft likely next document
  -> produce morning brief and next actions
  -> notify lawyer for review/approval
```

Approval rule:
- The living agent may read, summarize, extract, draft, analyze, and recommend.
- It must not file, send emails/notices, message clients, or mutate external systems without explicit approval.

### 8B. Bulk Document Intelligence

The lawyer should be able to upload 50+ documents, PDFs, images, scanned copies, emails, and matter notes into a project. LexAgent should turn that pile into structured matter knowledge.

MVP pipeline:
1. Store original file with matter ID and provenance.
2. Extract text with `pdfplumber` where possible.
3. Use OCR fallback only for scanned/image files.
4. Chunk text and save `document_chunks`.
5. Extract dates, parties, amounts, courts, document types, and key events.
6. Build chronology and evidence table.
7. Link every extracted fact/date to source document/page.
8. Queue research memo, risk memo, next actions, and draft jobs.

Outputs:
- Chronological fact sheet.
- Document index.
- Evidence table.
- Missing-document list.
- Research memo.
- Risk analysis.
- Draft candidates.

Scale path:
- Move files to S3/R2-compatible object storage.
- Add Qdrant for semantic retrieval across matter documents.
- Add stronger OCR/document parsing service only after real scanned-doc volume justifies it.

### 8C. Learning Loop

LexAgent should become better over time, but not through vague self-modifying magic. Learning must be explicit, reviewable, and reversible.

Learning signals:
- Lawyer edits to drafts.
- Accepted/rejected authorities.
- Preferred clauses and argument structures.
- Jurisdiction-specific checklist notes.
- Repeated workflow patterns.
- Feedback ratings and corrections.
- Compliance outcomes and missed-risk corrections.

MVP implementation:
- Store feedback in `feedback_items`.
- Store reusable drafting preferences in `style_preferences`.
- Store matter-type/court-specific observations in `playbook_notes`.
- Use these records in future prompts and planner templates.
- Suggest skill/playbook updates; do not silently rewrite core prompts.

Scale implementation:
- Add skill versioning, evals, and quality scores.
- Train retrieval over prior successful matters.
- Build firm-level playbooks from repeated accepted patterns.

## 9. Legal Knowledge Architecture

Current RAG is insufficient because law is relational and precedential.

Target:

```text
Legal Knowledge Layer
  Raw Sources
    Indian Kanoon, eCourts, SCC, Gazette, MCA, SEBI, RBI, firm docs
  Document Store
    original text, pages, provenance
  Vector Store
    semantic retrieval over chunks and propositions
  Knowledge Graph
    cases, courts, judges, statutes, sections, principles, issues
  Citation Verifier
    authority text + page/paragraph grounding + treatment
```

Nodes:
- Case
- Judge
- Court
- Statute
- Section
- Regulation
- Principle
- Issue
- Party
- Document

Relations:
- `OVERRULES`
- `FOLLOWS`
- `DISTINGUISHES`
- `APPLIES`
- `INTERPRETS`
- `CITES`
- `AUTHORED_BY`
- `DECIDED_BY`
- `HAS_SECTION`
- `RAISES_ISSUE`

Storage:
- Postgres for source registry and metadata.
- Qdrant for chunks/propositions.
- Kuzu/Neo4j/Postgres edge tables for graph.
- Object store for full PDFs/text.

## 10. Research System Redesign

Investigation Agent process:

```text
Plan
  -> Search
  -> Read
  -> Extract propositions
  -> Form hypotheses
  -> Search again for support/adverse law
  -> Compare authorities
  -> Verify citations
  -> Conclude with confidence and gaps
```

Sources:
- Indian Kanoon: broad case law search and fetch.
- eCourts: matter status, orders, cause list where available.
- SCC/paid databases: connector-ready, not assumed.
- Gazette: notifications and amendments.
- MCA: companies, filings, charges.
- SEBI: orders, circulars, enforcement.
- RBI: master directions, circulars, FAQs.

Citation verification pipeline:
1. Parse citation and authority title.
2. Fetch source text from primary/allowed source.
3. Locate quoted/proposition text.
4. Verify paragraph/page.
5. Check court hierarchy and binding value.
6. Check treatment: overruled, distinguished, followed, pending appeal.
7. Produce `CitationVerification` object.
8. Block final output or mark as human-review required if verification fails.

## 11. Reflection Architecture

```text
Draft
  -> Critic: legal validity
  -> Revision
  -> Critic: authorities and citation accuracy
  -> Revision
  -> Critic: procedure and maintainability
  -> Revision
  -> Critic: logic and persuasiveness
  -> Senior Counsel approval
```

Review dimensions:
- Legal validity
- Authorities
- Procedure
- Logic
- Persuasiveness
- Citation accuracy
- Risk to client
- Missing facts/evidence

The verification report must be stored with every draft version.

## 12. Legal Skill OS

Current markdown skills are a good seed. Target skill package:

```text
skills/
  writ_skill/
    skill.yaml
    prompts/
    workflows/
    tools.yaml
    memory/
    evals/
    templates/
```

Skill manifest fields:
- `name`
- `version`
- `jurisdiction`
- `matter_types`
- `triggers`
- `required_inputs`
- `workflow_dag`
- `tools_allowed`
- `approval_gates`
- `verification_policy`
- `output_templates`
- `tests`

Core skills:
- `writ_skill`
- `arbitration_skill`
- `contract_skill`
- `trademark_skill`
- `nclt_skill`
- `consumer_skill`
- `ni_act_138_skill`
- `bail_skill`
- `legal_notice_skill`

## 13. Gateway Architecture

Unified model:

```text
Telegram / WhatsApp / Slack / Discord / Voice / Web / CLI
  -> Thin Adapter
  -> Control Plane
  -> Auth + Tenant + Rate Limit + Audit
  -> Runtime
  -> Matter Workspace
  -> Notification Dispatcher
  -> Thin Adapter
```

Thin adapters should:
- Authenticate user/channel.
- Normalize incoming messages/files/events.
- POST to control plane.
- Render response/events.

They should not:
- Build graphs.
- Hold matter state.
- Run research.
- Bypass security.

## 14. Beast Terminal: Legal IDE

The terminal should be a runtime client, not a separate product.

Panes:
- Matter Explorer
- Research
- Documents
- Timeline
- Tasks
- Agent Status
- Memory
- Terminal/chat

Implementation:
- Use Textual for Python unless the team wants a Go TUI. The repo is Python; Textual minimizes split-stack complexity.
- UI subscribes to runtime events over WebSocket.
- All panes are projections over Matter Workspace objects.
- Agent Status shows execution DAG nodes, running tools, approvals, warnings, retries.
- Research pane shows authorities, treatment, verification status, and source excerpts.
- Documents pane supports draft versions, redlines, generated bundles.

## 15. Security Architecture

Preserve enterprise requirements. Do not simplify.

Required final state:
- Dual mode: personal mode zero-friction; enterprise mode enforced.
- JWT access token, refresh rotation, API keys.
- RBAC matrix: admin, partner, associate, viewer.
- Tenant isolation on every Postgres/SQLite/Qdrant/object-store query.
- AES-256-GCM at rest with HKDF per-firm keys.
- TLS enforcement and secure headers in enterprise mode.
- Audit log with 7-year retention.
- Rate limits and budget caps.
- GDPR/DPDP export and erasure workflows.
- Key rotation CLI.
- Secrets backend: env, Vault, AWS.
- CORS wildcard forbidden in enterprise mode.

Important contradiction resolved:
- `Security_features.md` suggests Fernet in places; `Enterprise_10x10_Plan.md` and live `security/crypto.py` correctly choose AES-256-GCM + HKDF. Keep AES-GCM.
- Security package exists, but control plane/session store do not use it consistently. Integration, not reinvention, is the next step.

## 16. Target Folder Structure

```text
lexagent/
  runtime/
    events.py
    event_bus.py
    jobs.py
    worker.py
    planner.py
    executor.py
    approvals.py
  workspace/
    models.py
    repository.py
    projections.py
    mutations.py
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
  chamber/
    senior.py
    planner.py
    research.py
    statutory.py
    procedure.py
    evidence.py
    drafting.py
    citation.py
    risk.py
    client.py
  memory/
    os.py
    working.py
    matter.py
    episodic.py
    semantic.py
    procedural.py
    firm.py
    lawyer.py
  knowledge/
    sources/
    graph.py
    vector.py
    citations.py
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

## 17. Roadmap

### Phase 1: Stabilize and Reconcile

Objective: make current claims true.
Dependencies: none.
Files: `control_plane.py`, `session_store.py`, `matter_memory.py`, `draft.py`, `cite.py`, tests.
Risks: breaking personal mode.
Effort: 2-3 weeks.
Why: the OS cannot stand on drift.

Work:
- Fix known critical issues: citation threshold, RAPTOR shape, matter memory injection.
- Wire `SecurityContext`, JWT, RBAC, audit, AES-GCM into control plane/session/memory paths.
- Remove stale static token path in enterprise mode.
- Add tenant columns/migrations and enforce them.

### Phase 2: Canonical Matter Workspace

Objective: create durable typed legal state.
Dependencies: Phase 1.
Files: new `workspace/`, migrations, repository, control plane endpoints.
Risks: duplicating LangGraph state.
Effort: 4-6 weeks.
Why: matter state must outlive chat, graph runs, and gateway sessions.

Core tables:
- `matters`, `parties`, `facts`, `issues`, `documents`, `document_chunks`
- `chronology_items`, `evidence_items`, `authorities`, `research_sessions`
- `drafts`, `deadlines`, `tasks`, `verification_reports`

### Phase 3: Living Agent MVP

Objective: make LexAgent work 24/7 on active matters.
Dependencies: Phase 2.
Files: new `runtime/jobs.py`, `runtime/worker.py`, scheduler, control plane job endpoints.
Risks: overengineering queue infra too early; runaway cost; doing external actions without approval.
Effort: 3-4 weeks.
Why: the highest-leverage behavior is waking up to completed matter work.

Work:
- Add Postgres `jobs` and `events` tables.
- Add `lex worker`.
- Add job types: document processing, chronology, research memo, risk analysis, deadline scan, morning brief, next actions.
- Add approval gates for any external/send/file action.

### Phase 4: Bulk Document Intelligence

Objective: upload 50+ documents and turn them into structured matter knowledge.
Dependencies: Phase 2 and 3.
Files: new `ingestion/`, document APIs, workspace repositories.
Risks: OCR cost/quality; hallucinated extraction; weak provenance.
Effort: 4-6 weeks.
Why: most legal work starts with messy documents, not clean prompts.

Work:
- Save original files.
- Extract text from PDFs/images/scans/emails.
- Chunk documents.
- Extract dates, parties, facts, issues, amounts, courts, document types.
- Build chronology, fact sheet, evidence table, missing-document list.
- Queue research memo, risk memo, and draft-next-document jobs.

### Phase 5: Verification and Research Memos

Objective: produce trustworthy research, citation, procedure, and risk outputs from the matter workspace.
Dependencies: Phase 2, 3, 4.
Files: `knowledge/`, `tools/grounding_verifier.py`, verification reports, research memo jobs.
Risks: false confidence; paid-source licensing; citation treatment accuracy.
Effort: 5-7 weeks.
Why: the living agent is only useful if its work is legally trustworthy.

Work:
- Store research memos as first-class workspace objects.
- Store risk analyses as first-class workspace objects.
- Strengthen citation grounding.
- Add procedure and limitation verification reports.
- Attach verification reports to drafts and memos.

### Phase 6: Learning Loop MVP

Objective: make LexAgent improve from lawyer edits, accepted authorities, rejected outputs, and repeated workflows.
Dependencies: Phase 2 and 5.
Files: new `learning/`, feedback tables, prompt/context injection.
Risks: vague "AI learns" claims; prompt drift; storing bad feedback as truth.
Effort: 3-5 weeks.
Why: the second biggest leverage feature is compounding quality over repeated tasks.

Work:
- Add `feedback_items`, `style_preferences`, `playbook_notes`.
- Capture draft edits/diffs.
- Track accepted/rejected authorities.
- Track jurisdiction/court-specific checklist notes.
- Suggest skill/playbook improvements; do not silently rewrite core prompts.

### Phase 7: Dynamic Planner and Execution DAG

Objective: replace static workflow expansion with planner-generated DAGs.
Dependencies: Phase 3, 4, 5.
Files: `runtime/planner.py`, `runtime/executor.py`, `graph.py`, chamber agents.
Risks: planner hallucinating steps.
Effort: 5-7 weeks.
Why: legal workflows vary by matter type, forum, evidence, and objective.

MVP simplification:
- Start with template plans for legal notice, writ petition, NI Act Section 138, arbitration, and contract review.
- Add LLM-generated plans only after template execution is stable.

### Phase 8: LexMemory OS

Objective: layered memory with governance.
Dependencies: Phase 2.
Files: `memory/os.py`, memory backends, vector store, extraction workers.
Risks: storing unverified facts as truth.
Effort: 5-6 weeks.
Why: persistent legal work requires separate factual, episodic, procedural, and firm memories.

MVP simplification:
- Treat Workspace + feedback + playbook notes as the first memory OS.
- Do not add Mem0/MemOS as mandatory infrastructure yet.

### Phase 9: Legal Knowledge Layer

Objective: authority graph + vector retrieval + citation verifier.
Dependencies: Phase 2, 5, 8.
Files: `knowledge/`, `tools/grounding_verifier.py`, `tools/citation_formatter.py`.
Risks: paid-source licensing; citation treatment accuracy.
Effort: 8-10 weeks.
Why: legal research cannot be pure vector search.

MVP simplification:
- Use Postgres authority records and edge tables first.
- Do not require Neo4j/Kuzu for the founder MVP.

### Phase 10: Investigation Research Agent

Objective: true plan/search/read/extract/hypothesize/re-search/compare/conclude loop.
Dependencies: Phase 5 and 9.
Files: `chamber/research.py`, `knowledge/sources/`.
Risks: cost and latency.
Effort: 6-8 weeks.
Why: retrieval is not research.

### Phase 11: Legal Chamber Subagents

Objective: specialist counsel agents with contracts and Senior Counsel coordinator.
Dependencies: Phase 7, 9, 10.
Files: `chamber/`, prompts, evals.
Risks: subagent bloat.
Effort: 8 weeks.
Why: legal output needs division of labor and adversarial review.

### Phase 12: Reflection and Verification

Objective: multi-pass draft-review-revision pipeline.
Dependencies: Phase 5 and 11.
Files: verification engine, draft versioning, report models.
Risks: slow final outputs.
Effort: 4-6 weeks.
Why: legal validity matters more than first-token latency.

### Phase 13: Legal Skill OS

Objective: package workflows, prompts, tools, templates, evals.
Dependencies: Phase 6, 7, and 11.
Files: `skills/registry.py`, skill package structure.
Risks: skill sprawl.
Effort: 5 weeks.
Why: skills are how the OS becomes extensible without graph bloat.

### Phase 14: Gateway Control Plane Completion

Objective: all gateways thin and secure.
Dependencies: Phase 1 and 3.
Files: `gateway/adapters/`, `control_plane.py`, notification dispatcher.
Risks: third-party platform churn.
Effort: 4-6 weeks.
Why: users should switch channels without losing matter state.

### Phase 15: Beast Terminal Legal IDE

Objective: Textual-based legal IDE over the runtime.
Dependencies: Phase 2 and 3.
Files: `ui/terminal/`.
Risks: terminal polish consuming core time.
Effort: 8-12 weeks.
Why: terminal becomes the power-user cockpit for persistent legal execution.

### Phase 16: Enterprise Hardening and Deployment

Objective: production SaaS posture.
Dependencies: all security integration.
Files: Docker, Caddy, migrations, admin CLI, observability.
Risks: compliance gaps hidden in connectors.
Effort: 6-8 weeks.
Why: legal data requires operational discipline.

## 18. Ruthless Simplification

### Keep

- LangGraph as execution substrate.
- Control plane.
- Thin gateway pattern.
- Skills, but upgrade to manifests.
- AES-256-GCM + HKDF.
- Postgres checkpointer, but treat it as run state only.
- Postgres jobs/events for the living agent MVP.
- Bulk document processing with strong provenance.
- Chronology, fact sheet, evidence table, research memo, risk analysis, morning brief, and next-action generation.
- Explicit learning loop from feedback, edits, accepted authorities, rejected outputs, and playbook notes.
- Qdrant retrieval, but add legal graph and verification.
- Matter memory concept, but replace markdown as source of truth.
- Terminal UI vision, but make it a runtime client.
- Citation enforcement gate.
- Voice gateway as optional adapter.
- Contract review/playbooks.

### Remove

- Claims that static token auth is enterprise auth.
- CORS wildcard in any enterprise path.
- Duplicate security modules/names from plans (`jwt_auth.py` vs `tokens.py`, `encryption.py` vs `crypto.py`) unless there is a real separate purpose.
- The idea that adding 30-60 `LexState` fields is a scalable architecture.
- "67-agent firm council" as a default product path.
- Any connector that bypasses policy, audit, tenant scope, or approval gates.
- File markdown memory as authoritative legal state.
- Any "self-learning" mechanism that silently rewrites prompts, skills, or playbooks without review.
- Any living-agent behavior that sends, files, or externally communicates without approval.

### Postpone

- Full 67-agent roster.
- LlamaParse as default ingestion; use local extraction/OCR fallback first.
- PageIndex until long-document retrieval is a measured bottleneck.
- Redline DOCX until draft versioning is stable.
- OpenAPI/MCP arbitrary connector marketplace.
- LLM council across providers.
- Translation filing mode.
- Email sending automation beyond approval-gated drafts.
- Paid SCC/Lexis/Westlaw integrations until licensing/product scope is clear.

## Final Product Principle

LexAgent OS V3 should be built around persistent legal execution:

```text
Living Matter Workspace
+ 24/7 Agent Worker
+ Bulk Document Intelligence
+ Planner
+ Learning Loop
+ Verification
```

Everything else is a client, adapter, skill, or source. If a feature does not help the lawyer wake up to better-organized matters, stronger drafts, verified authorities, clearer risks, and concrete next actions, it waits.
