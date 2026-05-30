# LexAgent Architecture Review V2: Founder Reality Check

Date: 2026-05-30.
Constraint model: one founder, occasional contributors, limited budget, ship production features quickly.
Source of truth: live repository and code review graph, not planning documents.

## 1. Repository Inventory

Code review graph snapshot:
- Files: 98
- Nodes: 997
- Edges: 7,831
- Languages: Python, Bash
- Tests: 379 test nodes across 29 test files
- Last graph update: 2026-05-30

Architectural communities:
- tools/search
- nodes/prompts
- gateway/control plane/Telegram
- memory/session/soul
- security/token
- voice
- CLI/chat
- skills
- scheduler/reminders
- contract/playbook

Hotspots:
- `LexConfig`
- `lexagent/nodes/research.py::run`
- `lexagent/nodes/cite.py::run`
- `lexagent/gateway/telegram.py::_run_graph_for_user`
- `lexagent/memory/matter_memory.py::save_matter_memory`
- `lexagent/cli.py`
- `lexagent/memory/soul.py::run_setup_wizard`

Large-file debt:
- `lexagent/cli.py`: 2,276 lines
- `lexagent/gateway/telegram.py`: 1,286 lines
- `lexagent/chat.py`: 591 lines
- `lexagent/gateway/voice.py`: 537 lines
- `lexagent/memory/soul.py`: 483 lines
- `lexagent/memory/session_store.py`: 461 lines
- `lexagent/nodes/intake.py`: 409 lines
- `lexagent/nodes/draft.py`: 369 lines
- `lexagent/gateway/control_plane.py`: 356 lines

## 2. Current Components

| Component | Purpose | Status | Technical Debt | Recommendation |
|---|---|---|---|---|
| LangGraph workflow | Intake -> research -> draft -> cite -> review | Implemented | Static graph, growing state, planner absent | Keep; add planner later as thin layer, not replacement now |
| `LexState` | Shared graph state | Implemented | Too many unrelated concerns in one `TypedDict` | Keep for graph; create typed Workspace models beside it |
| CLI | Main product surface and admin UX | Implemented | Huge file, many responsibilities | Keep; split commands after MVP workspace lands |
| Chat loop | Conversational shell with tools | Implemented | Separate from graph; can confuse product model | Keep as power-user mode; do not expand before workspace |
| Control plane | HTTP/WebSocket backend | Partially implemented | Static token auth, wildcard CORS, stubs, security package not wired | Make production-safe before adding gateways |
| Telegram gateway | Mobile/chat gateway | Implemented | Large file, still contains orchestration logic | Keep; simplify to control-plane client |
| Voice gateway | Voice/WebSocket/Twilio path | Partially implemented | Nice but non-core; adds dependency and UX burden | Postpone except demo/stub support |
| Matter memory | Per-matter markdown and state snapshot | Partially implemented | Markdown, no typed objects, no provenance, no tenant isolation | Replace gradually with Workspace tables |
| Session store | SQLite sessions, chat messages, reminders | Implemented | Schema v1, no firm/user columns, plaintext state | Keep for personal mode; migrate enterprise to Postgres |
| SOUL/lawyer memory | Lawyer profile/preferences | Implemented | File-based, setup wizard oversized | Keep file fallback; add simple DB profile later |
| Skills | Markdown skills with frontmatter | Implemented | No manifest/workflow/evals/versioning | Keep simple; do not build skill ecosystem yet |
| Tool registry | Decorator-based tool registration | Implemented | No policy, tenant namespace, approval gates | Keep; add tool audit/approval metadata only |
| Research | Kanoon, API/fallback, Tavily optional, limitation | Implemented/partial | Legacy and API paths overlap; "ReAct" is not truly ReAct | Simplify around one research path with citation gate |
| Retriever | BM25 + TF-IDF, Qdrant optional | Implemented/partial | Two retrieval modes; Qdrant operational burden | Keep local retriever; Qdrant only when needed |
| Legal KG | Regex in-memory GraphRAG | Implemented as lightweight tool | Not a real authority graph | Keep as extraction utility; do not add Neo4j |
| Citation verification | Cite node and citation gate | Implemented/partial | Needs stronger source grounding and thresholds | Build immediately; this is moat |
| Draft/review | Draft generation, review, docx | Implemented | Review is basic, not multi-pass legal verification | Improve review before adding agents |
| Contract review | Contract playbooks and node | Implemented/partial | Separate workflow path, not workspace-integrated | Keep if users value it; integrate later |
| Scheduler/reminders | Hearing reminders via Telegram job queue | Implemented | Not a general runtime | Keep; evolve immediately into living-agent jobs |
| Living Agent | 24/7 background work: process docs, summarize mail/docs, build facts/research/tasks overnight | Not started | High leverage, but dangerous if overbuilt | Build MVP now with Postgres jobs + one worker |
| Learning Loop | Improves drafting/research/checklists from user corrections and repeated patterns | Not started | Can become vague "AI learns" slop | Build explicit feedback memory and reusable playbooks, not magic learning |
| Security package | Context, crypto, tokens, audit, permissions | Partially implemented | Exists but not fully wired into app paths | Integrate now; do not invent new security modules |
| Providers/BYOK config | Provider profile/config | Partially implemented | Config sprawling | Keep; avoid per-user BYOK until enterprise users ask |
| Terminal UI | Spinner/live only | Partially implemented | Beast Terminal is plan-only | Postpone full TUI; build small matter dashboard first |
| Object storage | Store documents outside local temp | Not started | Uploaded docs saved temp/local | Use local filesystem first; S3-compatible later |
| Multi-agent chamber | Specialist agents | Planned | No runtime support | Postpone; use role prompts in verification first |
| Event runtime | Durable events/jobs | Not started | Reminders only | MVP: Postgres jobs/events, no NATS/Kafka |
| Matter Workspace | Typed legal matter state | Not started | Core missing product primitive | Build immediately |

## 3. Architecture Reality Audit

### Matter Workspace

Why it exists: lawyers work on matters, not chats.
Problem today: state is scattered across `LexState`, markdown, SQLite, checkpoints, and generated files.
If not built: LexAgent remains a drafting bot.
Simpler solution: Postgres tables for `matters`, `facts`, `documents`, `authorities`, `drafts`, `tasks`, `deadlines`.
Real bottleneck: yes.
Solo maintainable: yes if kept boring.

Verdict: KEEP, build immediately.

### Planner

Why it exists: legal notice, writ, arbitration, NI Act, and contract review require different steps.
Problem today: static graph forces all workflows through one pipeline.
If not built: feature growth turns `graph.py` and `LexState` into a maze.
Simpler solution: template-based plans first, not autonomous DAG synthesis.
Real bottleneck: soon, but not before workspace.
Solo maintainable: yes if declarative YAML/JSON plans.

Verdict: SIMPLIFY. Build plan templates before LLM planner.

### Verification

Why it exists: legal AI is judged by reliability.
Problem today: citation gate helps, but legal/procedural review is thin.
If not built: product cannot be trusted for litigation work.
Simpler solution: deterministic verification checklist plus one critic pass.
Real bottleneck: yes, immediate.
Solo maintainable: yes.

Verdict: KEEP, build immediately.

### Research

Why it exists: Indian legal output needs authorities and current law.
Problem today: search/fetch exists but investigation loop does not.
If not built: drafts are generic and risky.
Simpler solution: one source pipeline with saved research sessions and verified authorities.
Real bottleneck: yes.
Solo maintainable: yes if sources are limited.

Verdict: KEEP, simplify sources.

### Memory OS / MemOS

Why it exists: persistent preferences, matter context, precedent reuse.
Problem today: memory is fragmented.
If not built: less continuity, but product can still ship.
Simpler solution: Postgres workspace + Qdrant optional + summaries.
Real bottleneck: partially real, but "Memory OS" branding is overkill.
Solo maintainable: no if built as a separate subsystem now.

Verdict: SIMPLIFY. Do not add Mem0/MemOS yet.

### Event Runtime

Why it exists: proactive reminders, background research, resumable jobs.
Problem today: only graph invocation and Telegram reminders exist.
If not built: product remains reactive; it will not feel like a 24/7 legal assistant.
Simpler solution: Postgres `jobs` and `events` tables plus one async worker.
Real bottleneck: yes, if "wake up and work is done" is a core product promise.
Solo maintainable: yes in MVP form.

Verdict: KEEP, but MVP only. Build a living-agent worker, not distributed infrastructure.

### Living Agent

Why it exists: the lawyer should wake up to completed useful work, not an empty chat box.
Problem today: LexAgent only works when invoked.
If not built: LexAgent competes with ChatGPT as a drafting tool instead of becoming a legal operations assistant.
Simpler solution: `jobs` table, `agent_worker`, scheduled scans, and approval gates.
Real bottleneck: yes; this is leverage and differentiation.
Solo maintainable: yes if limited to a few job types.

MVP job types:
- `process_uploaded_documents`
- `build_chronology`
- `extract_facts_and_issues`
- `create_research_memo`
- `create_risk_analysis`
- `deadline_scan`
- `morning_brief`
- `next_actions`

Strict rule: the living agent can draft, summarize, extract, and recommend. It should not file, send, or communicate externally without approval.

Verdict: KEEP, build immediately after Workspace foundation.

### Learning Loop

Why it exists: LexAgent should improve from repeated work, lawyer edits, successful drafts, and rejected research.
Problem today: skills and SOUL exist, but there is no structured feedback loop.
If not built: every matter starts too cold.
Simpler solution: save feedback, edits, preferred clauses, accepted authorities, rejected arguments, and checklist outcomes.
Real bottleneck: yes, but only if learning is explicit and reviewable.
Solo maintainable: yes if built as records and playbooks.

MVP learning objects:
- draft feedback
- lawyer edits/diffs
- accepted/rejected authorities
- preferred clause/style snippets
- jurisdiction-specific checklist notes
- repeated workflow patterns

Avoid: vague autonomous self-modifying prompts.

Verdict: KEEP as explicit feedback memory, not a black-box learner.

### Legal Knowledge Graph / Neo4j

Why it exists: cases/statutes have relationships.
Problem today: current legal KG is regex in-memory extraction.
If not built: research can still work via verified authority records.
Simpler solution: `authorities` table with `treatment`, `court`, `proposition`, `verified_excerpt`.
Real bottleneck: imagined future bottleneck.
Solo maintainable: Neo4j no; authority table yes.

Verdict: POSTPONE Neo4j. Keep lightweight extraction only.

### Multi-Agent Councils

Why it exists: adversarial review and specialist perspectives.
Problem today: verification needs strengthening.
If not built: no harm if single critic is strong.
Simpler solution: sequential role prompts: Research -> Draft -> Critic -> Citation.
Real bottleneck: mostly imagined now.
Solo maintainable: no at large scale.

Verdict: POSTPONE. Do not build council.

### Beast Terminal

Why it exists: power-user legal IDE.
Problem today: UX mostly CLI/Telegram.
If not built: product can still sell if outputs and workspace are good.
Simpler solution: CLI commands + minimal web/control-plane dashboard.
Real bottleneck: not yet.
Solo maintainable: full TUI no; small dashboard yes.

Verdict: POSTPONE full TUI. Build minimal matter view.

### Enterprise Security

Why it exists: legal data requires trust.
Problem today: security package exists but app still has dev shortcuts.
If not built: cannot credibly serve firms.
Simpler solution: wire existing package only; do not add Vault/AWS until needed.
Real bottleneck: yes for paid pilots.
Solo maintainable: yes if minimal.

Verdict: KEEP, integrate now.

## 4. Mandatory Challenge Decisions

| Subsystem | Decision | Reason |
|---|---|---|
| Neo4j | REMOVE now / POSTPONE indefinitely | Operational burden too high; authority tables solve 80% |
| Knowledge Graph | SIMPLIFY | Keep regex extraction and authority relations in Postgres |
| NATS | POSTPONE | Postgres jobs/events are enough |
| Kafka | REMOVE | Wrong scale and maintenance profile |
| Temporal | POSTPONE | Great later; too heavy for founder MVP |
| Redis Streams | POSTPONE | Add only if Postgres queue becomes a bottleneck |
| Agent Marketplace | REMOVE | Distracts from legal execution moat |
| Multi-Agent Councils | POSTPONE | Use simple critic/revision loop |
| MemOS | SIMPLIFY | Use Postgres + optional Qdrant; no separate memory infra |
| Advanced Event Sourcing | REMOVE | Event log yes; event-sourced system no |
| Custom Protocols | REMOVE | REST/WebSocket/internal Python calls are enough |
| Large Skill Ecosystem | POSTPONE | Keep 5-8 high-value skills only |

## 5. MVP vs Scale Design

| Subsystem | MVP Version | Scale Version |
|---|---|---|
| Runtime | Postgres `jobs` table, one async worker, APScheduler for cron | Temporal or durable task queue only after workload justifies it |
| Events | Postgres `events` append table + in-process subscribers | NATS/Redis Streams |
| Living Agent | Background worker processes queued matter jobs overnight and posts morning brief | Worker pool with durable queue and richer scheduling |
| Document Intake | Upload folder/API, OCR fallback, extraction jobs, chronology/fact tables | Dedicated ingestion service, object storage, scalable OCR pipeline |
| Learning | Feedback tables, draft diffs, accepted/rejected research, playbook updates | Dedicated evaluation/memory service and skill versioning |
| Memory | Postgres workspace + summaries + optional Qdrant per matter | Dedicated memory service with policies/extraction pipelines |
| Research | Kanoon API/fallback, uploaded docs, verified authorities table | Multi-source connectors, treatment graph, paid DB integrations |
| Planner | YAML/JSON plan templates per workflow | LLM-generated DAG with validation |
| Verification | Citation gate + deterministic checklist + one critic pass | Multi-pass specialist verification engine |
| Storage | Postgres + local filesystem | Postgres + S3/R2 + Qdrant cluster |
| Security | JWT/RBAC/audit/encryption integrated into existing app | Enterprise SSO, KMS, Vault, org admin console |
| UI | CLI + control-plane endpoints + simple matter dashboard | Full legal IDE/TUI/web app |
| Skills | Curated built-in skills | Versioned skill packages and registry |
| Gateways | CLI + Telegram + web/control plane | WhatsApp/Slack/Discord/voice after PMF |

## 6. Complexity Budget

Scores: Value 1-10, Complexity 1-10, Maintenance 1-10.

| Component | Value | Complexity | Maintenance | Keep? |
|---|---:|---:|---:|---|
| Matter Workspace | 10 | 5 | 5 | Yes |
| Citation Verification | 10 | 4 | 4 | Yes |
| Research Sessions | 9 | 5 | 5 | Yes |
| Simple Planner Templates | 8 | 3 | 3 | Yes |
| Enterprise Security Wiring | 8 | 5 | 5 | Yes |
| Living Agent Worker | 10 | 5 | 5 | Yes |
| Document Intake Pipeline | 10 | 6 | 6 | Yes |
| Learning Feedback Loop | 9 | 4 | 4 | Yes |
| Postgres Jobs/Events | 9 | 4 | 4 | Yes |
| Qdrant | 6 | 6 | 6 | Optional |
| Telegram Gateway | 7 | 5 | 5 | Yes, simplify |
| Voice Gateway | 3 | 6 | 6 | No, postpone |
| Full TUI | 4 | 8 | 8 | No, postpone |
| Neo4j | 3 | 8 | 8 | No |
| Temporal | 3 | 8 | 8 | No now |
| NATS | 2 | 7 | 7 | No now |
| Kafka | 1 | 10 | 10 | No |
| Mem0/MemOS | 5 | 7 | 7 | No now |
| Multi-Agent Council | 4 | 8 | 8 | No now |
| Agent Marketplace | 1 | 9 | 9 | Delete |
| Arbitrary MCP/OpenAPI connectors | 3 | 8 | 8 | Postpone |

Rule: for the next 6 months, reject anything with Value < 7 and Complexity > 6.

## 7. Infrastructure Cost Audit

| Infrastructure | Operational Burden | Classification | Reason |
|---|---|---|---|
| Postgres | Medium | Required Now | Workspace, jobs, events, auth, audit, checkpointing |
| Qdrant | Medium | Required Later / Optional Now | Useful for docs, but local retriever can ship first |
| Redis | Medium | Required Later | Only needed for queues/cache at scale |
| Neo4j | High | Never Required for MVP | Authority table/edge table is enough |
| Temporal | High | Required Later only if jobs become complex | Premature today |
| NATS | Medium-High | Required Later only under multi-worker event load | Postgres events first |
| Kafka | Very High | Never Required | Wrong for founder-led legal SaaS |
| Object Storage | Low-Medium | Required Later | Start local; add S3/R2 before multi-tenant production docs |

Minimum production stack:
- Postgres
- App server
- Local filesystem or S3-compatible bucket
- Optional Qdrant

That is it.

## 8. Technical Moat Analysis

A lawyer will not choose LexAgent over Harvey, CoCounsel, Claude, ChatGPT, or Gemini because of better prompts, more agents, or more RAG.

The actual moat:

1. Indian litigation workflow specificity.
2. Persistent matter workspace that remembers facts, evidence, deadlines, drafts, orders, authorities, and strategy.
3. Citation and procedural verification that produces auditable confidence, not just fluent text.
4. Local/legal-ops ergonomics: CLI/Telegram-friendly, matter-centric, fast to use in a real chamber.
5. Practitioner-owned data and workflows: skills/playbooks adapted to Indian courts and firm style.
6. Price/accessibility for Indian lawyers and smaller firms.

Feature ranking by moat strength:

| Feature | Moat Strength |
|---|---:|
| Matter Workspace | 10 |
| Citation Verification | 10 |
| Indian Research Workflow | 9 |
| Procedure/Limitation Checks | 9 |
| Evidence/Timeline Mapping | 8 |
| Draft Versioning | 8 |
| Firm/Lawyer Style Memory | 7 |
| Telegram/CLI workflows | 7 |
| Full TUI | 5 |
| Voice | 4 |
| Multi-agent councils | 3 |
| Agent marketplace | 1 |
| Kafka/NATS/Neo4j | 1 |

## 9. Ruthless Prioritization

### Tier 1: Build Immediately

- Matter Workspace in Postgres.
- Living Agent MVP with Postgres jobs and one background worker.
- Bulk document upload and processing pipeline.
- Chronology/fact/evidence extraction from uploaded documents.
- Security integration for existing control plane.
- Citation verification hardening.
- Research session model with saved authorities.
- Procedure and limitation checklist objects.
- Draft versioning.
- Template planner for 3 workflows: legal notice, writ petition, NI Act S.138.
- File/document persistence with provenance.
- Morning brief / next-actions summary.
- Learning feedback loop from edits, accepted authorities, rejected outputs, and repeated workflows.

### Tier 2: Build Later

- Qdrant as persistent matter document retrieval.
- Simple Postgres jobs/events worker.
- Minimal matter dashboard.
- WhatsApp gateway if users demand it.
- Firm/lawyer memory in DB.
- Redline docx.
- Contract review workspace integration.

### Tier 3: Postpone Until PMF

- Full Beast Terminal.
- Voice as production channel.
- Mem0/MemOS service.
- Temporal.
- NATS/Redis Streams.
- Paid legal database integrations.
- Multi-provider LLM council.
- Translation filing mode.
- Arbitrary MCP/OpenAPI connector platform.

### Tier 4: Delete

- Kafka.
- Agent marketplace.
- 67-agent council as product feature.
- Custom protocols.
- Advanced event-sourced architecture.
- Neo4j as required dependency.
- Large skill ecosystem before users repeatedly ask for it.

## 10. MVP Architecture

Smallest founder-led architecture capable of becoming OpenClaw for legal:

```text
CLI / Telegram / Minimal Web
  -> FastAPI Control Plane
    -> JWT/RBAC/Audit
    -> LangGraph Workflow
    -> Template Planner
    -> Matter Workspace Repository
      -> Postgres
      -> Local/S3 Document Store
    -> Job Queue
      -> Living Agent Worker
    -> Research + Citation Verification
    -> Document Processing + Chronology Builder
    -> Draft Versioning
    -> Optional Qdrant
```

Tables to build first:
- `firms`
- `users`
- `matters`
- `parties`
- `facts`
- `documents`
- `evidence_items`
- `authorities`
- `research_sessions`
- `drafts`
- `deadlines`
- `tasks`
- `events`
- `jobs`
- `audit_log`
- `document_chunks`
- `extracted_dates`
- `chronology_items`
- `feedback_items`
- `style_preferences`
- `playbook_notes`

No Neo4j. No Temporal. No NATS. No Kafka. No multi-agent council.

## 11. Scale Architecture

Only after paid usage and many active matters:

```text
Gateways
  -> Control Plane
  -> Runtime API
  -> Worker Pool
  -> Postgres core DB
  -> Object Storage
  -> Qdrant cluster
  -> Redis/NATS for events if needed
  -> Temporal if workflows become long and failure-prone
```

Scale rule:
- Add infra only when a current component is objectively failing.
- Postgres first.
- Qdrant second.
- Object storage before multi-tenant file production.
- Redis/NATS only when in-process/Postgres notifications are insufficient.
- Temporal only when workflow durability becomes painful.

## 12. 12-Month Roadmap

### Months 1-2: Workspace + Living Agent Foundation

Goal: make current product matter-centric and proactive.

Build:
- Postgres matter schema.
- `jobs` table and one background worker.
- Bulk document upload path.
- Document processing job: PDF/text/image/scanned copy extraction with fallback path.
- Chronology/fact/evidence extraction into Workspace tables.
- Morning brief and next-actions job.
- Wire existing `security/` package into `control_plane.py`.
- Add tenant/auth/audit/encryption path for production mode.
- Remove dev CORS in enterprise mode.
- Fix research/citation known risks.
- Refactor only the worst hotspots if blocking work.

Ship:
- A matter that can ingest documents and produce chronology, facts, tasks, and morning brief.

### Months 3-4: Verification + Research Memos

Goal: turn extracted matter material into verified legal work.

Build:
- Authority records.
- Draft versions.
- Deadline/task records.
- Research memo job.
- Risk analysis job.
- Citation grounding report.
- Procedure/limitation checklist.

Ship:
- `lex matter show`
- `lex matter facts`
- `lex matter authorities`
- `lex matter drafts`
- `lex matter chronology`
- `lex matter brief`

### Months 5-6: Learning Loop + Indian Workflow Depth

Goal: make LexAgent improve from use.

Build:
- Feedback capture after every draft/research memo.
- Save lawyer edits/diffs.
- Accepted/rejected authority tracking.
- Jurisdiction-specific checklist notes.
- Reusable playbook notes.

Ship:
- Verified legal notice.
- Verified writ petition.
- Verified NI Act S.138 complaint checklist/draft.
- Improved second/third drafts based on prior edits.

### Months 7-8: Planner Templates and Jobs

Goal: predictable execution without distributed systems.

Build:
- Template planner for top workflows.
- Postgres jobs table.
- Async worker for background research/deadlines.
- Event table for UI/projections.

Ship:
- Resumable tasks.
- Deadline radar.
- Background research.

### Months 9-10: Retrieval and Knowledge Upgrade

Goal: better matter-specific research.

Build:
- Qdrant-backed matter document retrieval if demand exists.
- Authority relation table: follows/distinguishes/overrules/applies.
- Research session compare view.

Ship:
- Saved research notebooks per matter.
- Reusable verified authorities.

### Months 11-12: Product Surface

Goal: make it usable daily.

Build:
- Minimal web/matter dashboard or focused Textual TUI.
- Telegram as thin control-plane client.
- WhatsApp only if users ask.
- Firm/lawyer memory in DB.

Ship:
- Daily usable legal workspace.
- Paid pilot readiness.

## 13. Things To Delete or Stop Saying

Delete from near-term plans:
- Kafka
- Neo4j requirement
- Temporal requirement
- NATS requirement
- Redis Streams requirement
- Agent marketplace
- 67-agent council
- Full MemOS implementation
- Full Beast Terminal as prerequisite
- Arbitrary connector platform
- "OpenAI/Anthropic-level architecture" framing

Stop saying:
- "Persistent Legal OS" unless Matter Workspace exists.
- "Enterprise security" until the security package is wired.
- "ReAct research" unless the loop actually plans, searches, reads, hypothesizes, and searches again.
- "Multi-tenant" unless every storage path filters by tenant.

## 14. Final Founder Recommendation

The best LexAgent is not a distributed systems showcase. It is a brutally useful Indian legal matter workspace with a 24/7 living agent and verified drafting.

The next architecture should be:

```text
Postgres Matter Workspace
+ Living Agent Worker
+ Bulk Document Processing
+ LangGraph pipeline
+ Citation/Procedure Verification
+ Research Sessions
+ Simple Planner Templates
+ Secure Control Plane
```

This maximizes leverage because it turns existing code into a product. It minimizes complexity because it avoids new infrastructure. It maximizes moat because it focuses on Indian legal workflow, persistent matter state, and trustworthy verification. It improves shipping velocity because the founder can build it one table, one endpoint, one workflow at a time.

The founder-sized bet:

Build the matter workspace, living agent worker, bulk document intelligence, and verification layer before building more agents.

If LexAgent wakes up before the lawyer, processes the matter file, builds the chronology, identifies gaps, drafts the next documents, verifies authorities, and learns from corrections, it has a real shot. If it chases councils, event buses, marketplaces, and graph databases now, it becomes a beautiful unpaid infrastructure project.
