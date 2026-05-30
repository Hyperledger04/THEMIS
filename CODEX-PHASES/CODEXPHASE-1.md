# CODEXPHASE-1

## Before

- LexAgent had a LangGraph drafting workflow, control plane, Telegram/voice gateways, research/citation nodes, and file/SQLite-based memory.
- There was no concrete agent runtime layer for living matter intelligence.
- Extracted facts/chronology/evidence did not have a shared source-citation model.
- Clickable document footnotes had no canonical web target.
- Provider support existed through profiles/config, but no runtime-facing provider-agnostic router.

## Implemented In This Phase

- Added Matter Workspace primitives:
  - `Matter`
  - `DocumentRecord`
  - `SourceAnchor`
  - `ExtractedFact`
  - `ChronologyItem`
  - `EvidenceItem`
- Added page + line citation anchors with viewer URLs.
- Added OpenClaw-style runtime models:
  - runs, jobs, steps, tool calls, artifacts, approvals, events.
- Added Postgres runtime schema for agent jobs, traces, approvals, notifications, artifacts, and source anchors.
- Added provider-agnostic `ModelRouter` over LiteLLM.
- Added `/document-viewer/{matter_id}/{document_id}` endpoint as the clickable footnote target.
- Added tests for runtime/workspace models, source anchors, provider router, and document viewer endpoint.

## Verification

- Full CRG rebuild completed:
  - 101 files parsed
  - 1,039 nodes
  - 8,178 edges
  - 107 flows
  - 15 communities
- Test suite:
  - `uv run pytest tests -q`
  - 404 passed, 2 warnings

## What This Enables Next

- `lex worker`
- document ingestion jobs
- source-cited chronology/fact/evidence extraction
- NI Act Section 138 living workflow
- Qdrant + PageIndex retrieval routing
- human approval workflow
