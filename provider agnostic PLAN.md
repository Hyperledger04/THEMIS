# Final Roadmap Addendum: Provider-Agnostic Agent Runtime + Source-Cited Living Matter Intelligence

## Summary

The final product architecture should now be centered on an **OpenClaw-style agent runtime**:

```text
Matter Workspace
+ Agent Runtime
+ Living Matter Intelligence
+ Source-Cited Extraction
+ Provider-Agnostic Model Layer
+ Human Approval
```

The living agent should not be a cron script wrapped around LangGraph. It should be a real runtime that can create jobs, run agents, use tools, pause for approval, resume work, notify users, and preserve traceability.

The critical verification feature is:

```text
Every extracted fact, chronology item, evidence entry, research proposition, and risk must carry a clickable citation footnote.
Clicking it opens the web document viewer at the exact page + extracted line anchor.
```

External reference to keep in mind: Mike is an OSS AI legal platform using a web frontend, backend, Postgres/Supabase-style storage, object storage, model-provider keys, and document workflows, which aligns with the direction here: https://github.com/willchen96/mike.

## Key Architecture Changes

### 1. Agent Runtime Becomes Core

Add an agent runtime layer before expanding workflows.

Runtime responsibilities:

```text
create_run
create_job
assign_agent
execute_tool
persist_trace
pause_for_approval
resume_after_approval
retry_failed_job
notify_user
record_output
record_cost
```

Runtime entities:

```text
agent_runs
agent_jobs
agent_steps
agent_tool_calls
agent_artifacts
agent_approvals
agent_notifications
agent_errors
agent_runtime_events
```

The runtime should support these agent types immediately:

```text
Document Processing Agent
Chronology Agent
Evidence Agent
NI Act Compliance Agent
Research Agent
Risk Agent
Drafting Agent
Verification Agent
Notification Agent
Learning Agent
```

Implementation rule:

```text
Use Postgres jobs/events for MVP.
Do not use Temporal/NATS/Kafka yet.
Keep those planned for later scale stages.
```

### 2. Provider-Agnostic Model Layer

The runtime must not be tied to Anthropic, OpenAI, Gemini, or any one provider.

Add a provider abstraction:

```text
ModelProvider
ModelRouter
ToolSchemaAdapter
ProviderCredentialStore
```

Required providers:

```text
Anthropic
OpenAI
Google Gemini
OpenRouter
Local/Ollama later
```

Runtime calls should use a provider-neutral interface:

```python
generate(messages, tools, model_profile, response_schema=None)
stream(messages, tools, model_profile)
embed(texts, embedding_profile)
```

Provider-specific details stay inside adapters:

```text
Anthropic tool schema
OpenAI tool schema
Gemini tool schema
LiteLLM fallback
```

Default MVP approach:

```text
Use LiteLLM where possible.
Add provider-specific adapters only where tool-calling or structured output differs.
```

### 3. Source-Cited Living Matter Intelligence

Every extracted item must be source-backed.

Objects requiring footnotes:

```text
facts
issues
chronology_items
evidence_items
document_summaries
research_memo propositions
risk_analysis points
draft factual assertions
NI Act compliance findings
```

Each item stores:

```text
source_document_id
source_page
source_line_start
source_line_end
source_excerpt
source_anchor_id
confidence
extractor_agent
extraction_run_id
```

Footnote format in UI:

```text
Cheque was dishonoured on 14 March 2026. [F3]
```

Clicking `[F3]` opens:

```text
/document-viewer/{matter_id}/{document_id}?page=4&line=27&anchor=F3
```

The viewer highlights the exact extracted line.

MVP anchor standard:

```text
Page + extracted line anchor
```

Later scale standard:

```text
Page + line + bounding-box coordinates for PDFs/images/OCR
```

### 4. Document Viewer and Citation Anchors

Add a web document viewer as the canonical verification surface.

Viewer requirements:

```text
open original document
jump to page
highlight extracted line
show source excerpt
show extracted object linked to that source
show confidence
show OCR/extraction method
```

For PDFs:

```text
page number + line index from extracted text
```

For OCR images/scans:

```text
page/image number + OCR line index
bounding boxes later
```

For DOCX:

```text
paragraph index + heading/section label
line-like anchor generated from extracted text
```

For emails later:

```text
message id + quoted line/paragraph anchor
```

### 5. NI Act Workflow Uses Runtime

The NI Act Section 138 workflow should be represented as a runtime plan, not just one graph path.

Runtime plan:

```text
1. process_uploaded_documents
2. extract_ni_act_entities
3. build_chronology
4. build_evidence_table
5. check_statutory_compliance
6. identify_missing_documents
7. retrieve_relevant_law
8. create_research_memo
9. create_risk_analysis
10. draft_notice
11. draft_complaint
12. verify_citations_and_facts
13. request_human_approval
14. notify_email_and_telegram
```

Each step creates traceable artifacts.

No step may create unsupported factual claims. Any unsupported item is marked:

```text
needs_source
```

and appears in the approval review.

### 6. Retrieval Routing Under Runtime

The runtime owns retrieval decisions.

Available retrieval modes:

```text
Qdrant semantic vector retrieval
PageIndex vectorless tree retrieval
BM25/local keyword fallback
Hybrid merged retrieval
```

Routing policy:

```text
Use PageIndex for long documents, page-aware questions, exact source verification.
Use Qdrant for semantic/factual similarity across many chunks.
Use both for drafting, research memos, risk analysis, and verification.
Log the routing decision for every retrieval step.
```

Store routing logs:

```text
retrieval_runs
retrieval_queries
retrieval_results
retrieval_routing_decisions
```

Each retrieved result must include source anchors where possible.

### 7. Human Approval Layer

Automatic work is allowed.

External action is not.

Allowed automatically:

```text
extract
summarize
classify
retrieve
draft
research
risk-analyze
update proposed skill version
prepare notification
```

Requires approval:

```text
send legal notice
email client/opponent
file complaint
mark document final
apply skill update to active production skill
delete matter data
share documents externally
```

Approval records:

```text
approval_id
matter_id
run_id
artifact_id
requested_action
risk_level
status
approved_by
approved_at
approval_notes
```

### 8. Learning Loop With Runtime Traces

The learning loop should use runtime artifacts and feedback.

Signals:

```text
lawyer edits
approval/rejection
manual correction to facts
manual correction to chronology
accepted/rejected authority
draft version diffs
skill update acceptance
```

Learning outputs:

```text
style preference
NI Act drafting preference
court-specific checklist note
research preference
risk checklist update
proposed skill version
```

Notification:

```text
“LexAgent updated your NI Act drafting skill based on your edits. Review here.”
```

Skill updates should be versioned.

Auto-update rule:

```text
Create new proposed skill/playbook version automatically.
Notify lawyer.
Use active version only after approval, unless user enables trusted auto-apply later.
```

## Implementation Order

### Phase 1: Runtime + Workspace Foundation

Build:

```text
Postgres Matter Workspace
Agent runtime tables
Job worker
Run/step/tool trace logging
Approval records
Notification records
Provider-agnostic model interface
```

Acceptance:

```text
A matter can create an agent run.
The run creates jobs.
The worker executes jobs.
Every step is traceable.
A job can pause for approval and resume.
Telegram/email notification can be queued.
```

### Phase 2: Source-Cited Document Intelligence

Build:

```text
LlamaParse primary ingestion
local fallback extraction
OCR path for images/scans
document chunks
source anchors
document viewer
footnote links
chronology/fact/evidence extraction
```

Acceptance:

```text
Upload a PDF/image/DOCX.
Agent extracts facts and chronology.
Every item has a footnote.
Clicking footnote opens viewer at page + line anchor.
Unsupported extracted claims are flagged.
```

### Phase 3: NI Act Section 138 Living Workflow

Build:

```text
NI Act runtime plan
compliance checklist
research memo
risk memo
notice draft
complaint draft
verification report
approval screen
morning brief
```

Acceptance:

```text
Upload cheque, return memo, notice proof, payment documents.
Agent builds chronology, evidence table, compliance checklist, research memo, risk memo, notice, complaint.
Every factual statement is source-cited.
Drafts are held for approval.
Telegram + email ping the lawyer.
```

### Phase 4: Retrieval Router

Build:

```text
Qdrant retriever
PageIndex retriever
Hybrid retrieval router
retrieval routing logs
source-aware result format
```

Acceptance:

```text
Short semantic query uses Qdrant.
Long document/page-aware query uses PageIndex.
Drafting/research verification uses both.
Routing decision is visible in runtime trace.
```

### Phase 5: Learning Loop

Build:

```text
feedback capture
draft diff capture
accepted/rejected authority tracking
skill version proposals
learning notifications
```

Acceptance:

```text
Lawyer edits a draft.
LexAgent creates a proposed NI Act skill/style update.
Lawyer receives Telegram/email notification.
Skill update is versioned and reviewable.
```

## Interfaces and Public Shapes

### Runtime Job Shape

```json
{
  "job_id": "job_...",
  "matter_id": "M-...",
  "run_id": "run_...",
  "type": "build_chronology",
  "status": "queued|running|paused|completed|failed",
  "agent": "chronology_agent",
  "requires_approval": false,
  "created_at": "...",
  "started_at": null,
  "completed_at": null
}
```

### Source Anchor Shape

```json
{
  "anchor_id": "F3",
  "document_id": "doc_...",
  "page": 4,
  "line_start": 27,
  "line_end": 29,
  "excerpt": "Cheque bearing no. 123456 was returned unpaid...",
  "viewer_url": "/document-viewer/M-001/doc_001?page=4&line=27&anchor=F3"
}
```

### Extracted Fact Shape

```json
{
  "fact_id": "fact_...",
  "matter_id": "M-001",
  "text": "The cheque was dishonoured on 14 March 2026.",
  "status": "extracted",
  "confidence": 0.86,
  "footnotes": ["F3"],
  "source_anchors": ["F3"]
}
```

### Provider-Agnostic Model Call

```python
await model_router.generate(
    messages=messages,
    tools=tools,
    model_profile="drafting_default",
    response_schema=ChronologyExtraction,
)
```

## Test Plan

Runtime tests:

```text
create run
enqueue job
worker executes job
worker records steps
tool call trace stored
job pauses for approval
approval resumes job
failed job retries
```

Provider tests:

```text
Anthropic/OpenAI/Gemini tool schemas normalize to common interface
structured output works through model router
provider failure falls back when configured
```

Document intelligence tests:

```text
PDF creates page + line anchors
image OCR creates line anchors
DOCX creates paragraph/line anchors
viewer URL opens correct page/line
extracted fact has footnote
chronology item has footnote
unsupported extraction is flagged
```

Retrieval tests:

```text
Qdrant route for semantic query
PageIndex route for page-aware query
hybrid route for draft/research verification
routing log persisted
retrieval result includes source anchor
```

NI Act tests:

```text
cheque fields extracted with citations
return memo fields extracted with citations
notice date/service extracted with citations
limitation checklist generated
notice draft saved for approval
complaint draft saved for approval
verification blocks uncited factual claims
```

Learning tests:

```text
draft edit creates feedback item
feedback creates proposed skill version
notification queued for skill update
active skill does not change without approval
```

## Assumptions

- The runtime is MVP Postgres-based, OpenClaw-like in behavior, but not a distributed system yet.
- The architecture is provider-agnostic from day one.
- Mike-inspired patterns are used for document workflows, versioning, provider keys, and web-first verification UX, adapted to LexAgent’s Python/Postgres stack.
- First clickable citation standard is page + extracted line anchor.
- First click target is the web document viewer.
- Bounding-box-level PDF/OCR highlighting comes later.
- Every extracted matter object must be source-cited or explicitly marked unsupported.
- All later big systems remain in the roadmap, but after the runtime + source-cited living matter workflow works end-to-end.
