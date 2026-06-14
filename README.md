# Themis

**Open-source AI agent for Indian litigation practice — built on LangGraph.**

Themis takes a matter brief from a lawyer, asks targeted clarifying questions, researches Indian case law via Indian Kanoon, drafts a court-ready document with verified citations, and saves the matter to persistent memory. It runs over Telegram, voice (browser WebSocket or Twilio phone), REST API, or CLI.

---

## What It Does

A lawyer types: *"I need to file a writ petition in Delhi HC challenging wrongful termination under Article 21"*

Themis:
1. Asks clarifying intake questions (parties, jurisdiction, facts, limitation)
2. Searches Indian Kanoon for binding precedents
3. Calculates the applicable limitation period
4. Drafts a full court-ready document with verified citations
5. Exports a `.docx` file with court-appropriate formatting
6. Saves the matter to memory for future sessions

---

## Architecture

All agent logic runs inside a **LangGraph StateGraph**. Every step is a node that reads from and writes to a shared `LexState` dictionary — no state lives inside node functions.

```
START
  ↓
[intake]   ← loops until all required fields are collected
  ↓
[research] ← Indian Kanoon search + limitation calculation
  ↓
[draft]    ← LLM drafts the document using SOUL.md + active skill
  ↓
[cite]     ← hybrid BM25 + TF-IDF citation verification
  ↓
[review]   ← quality check + .docx export
  ↓
END
```

Contract review follows a separate branch: `intake → contract_review → END`.

---

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Set your API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# 3. First-time setup (creates ~/.themis/SOUL.md)
python -m themis.cli setup

# 4. Draft your first document
python -m themis.cli draft "writ petition Delhi HC wrongful termination Article 21"

# 5. Run the test suite
pytest tests/ -v
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Agent framework | LangGraph ≥ 0.2 |
| LLM | `claude-sonnet-4-6` via LiteLLM (swap to any provider via `.env`) |
| API | FastAPI + Uvicorn |
| CLI | Typer + Rich |
| Persistent state | Postgres + `langgraph-checkpoint-postgres` |
| Session history | SQLite + FTS5 |
| Vector retrieval | Qdrant + sentence-transformers (optional) |
| BM25 retrieval | rank-bm25 |
| Document output | python-docx |
| PDF parsing | pdfplumber |
| Telegram | python-telegram-bot |
| Voice (STT/TTS) | Whisper / Deepgram / ElevenLabs / Google TTS (opt-in) |
| Scheduling | APScheduler |
| Package manager | uv |

---

## Key Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Claude API key |
| `LEX_MODEL` | `claude-sonnet-4-6` | LLM to use |
| `LEX_KANOON_BACKEND` | `stub` | `stub` / `api` / `mcp` |
| `DATABASE_URL` | none | Postgres for persistent checkpoints |
| `TELEGRAM_BOT_TOKEN` | none | Telegram bot |
| `LEX_QDRANT_ENABLED` | `false` | Persistent vector retrieval |
| `LEX_VOICE_ENABLED` | `false` | Voice gateway |

All config lives in `themis/config.py` as `LexConfig(BaseSettings)`.

---

## Gateways

| Gateway | How to start |
|---|---|
| CLI | `python -m themis.cli draft "..."` |
| Telegram bot | `python -m themis.cli gateway telegram` |
| Control plane (REST + WebSocket) | `python -m themis.gateway.control_plane` |
| Voice (browser WebSocket) | Connect to `ws://host:8000/voice/ws/{session_id}` |
| Voice (Twilio phone) | Configure Twilio webhook to `POST /voice/incoming` |

All gateways funnel into the same FastAPI control plane. Matter state is shared — start on Telegram, continue via REST.

---

## Memory

| Layer | Location | What it stores |
|---|---|---|
| SOUL.md | `~/.themis/SOUL.md` | Lawyer identity, bar details, drafting style |
| Matter memory | `~/.themis/matters/{id}/MEMORY.md` | Per-matter state snapshots (human-readable) |
| Session history | `~/.themis/sessions.db` | Searchable SQLite log with FTS5 |
| LangGraph checkpoints | Postgres | Full agent state per node — resumable after crash |

---

## Skills System

Skills are `.md` files with YAML frontmatter. Dropping a file into `~/.themis/skills/` creates a custom skill — no code required.

```yaml
---
name: writ_petition
trigger_keywords: [writ, HC, Article 226, fundamental rights]
matter_types: [writ_petition]
---
# Mandatory sections, drafting conventions, relevant statutes...
```

Bundled skills: civil litigation, criminal litigation, legal notice, contract review, argument patterns.

---

## Tools

| Tool | Purpose |
|---|---|
| `kanoon.py` | Indian Kanoon search (stub / API / MCP backends) |
| `limitation.py` | Limitation period calculator under the Limitation Act 1963 |
| `retriever.py` | Hybrid BM25 + TF-IDF citation verifier; optional Qdrant |
| `chunker.py` | Parent-child document chunker for RAG |
| `reranker.py` | LLM re-ranker for retrieved passages (optional) |
| `raptor_summarizer.py` | Hierarchical cluster summaries for complex queries (optional) |
| `legal_kg.py` | Legal entity knowledge graph / GraphRAG (optional) |
| `docx_writer.py` | Court-formatted `.docx` export |
| `court_fees.py` | Court fees calculator |

---

## V3 Roadmap

Themis is evolving into a persistent legal operating system — a **Living Matter Workspace** that works 24/7 on active matters:

- Canonical matter workspace (Postgres-backed typed legal objects)
- `lex worker` — background job runner for document processing, chronology building, research memos, risk analysis, morning briefs
- Bulk document intelligence — upload 50+ PDFs/scans → structured chronology, fact sheet, evidence table
- Dynamic planner — LLM-generated execution DAGs per matter type
- Legal Chamber subagents — Senior Counsel, Research Counsel, Evidence Counsel, Drafting Counsel, Risk Counsel
- LexMemory OS — layered working / matter / episodic / semantic / procedural / firm / lawyer memory
- Learning loop — lawyer edits, accepted authorities, and feedback improve future drafts

See [`THEMIS_OS_V3_ARCHITECTURE_ROADMAP.md`](THEMIS_OS_V3_ARCHITECTURE_ROADMAP.md) for the full plan.

---

## Current Status

**Phase 8B complete — 404 tests passing.**

Built and working: full LangGraph pipeline, CLI, Telegram gateway, voice gateway, REST/WebSocket control plane, SOUL.md + matter memory + SQLite sessions, Postgres checkpointing, hybrid RAG retrieval, skills system, `.docx` output, contract review, limitation calculator, court fees calculator, multi-provider LLM support via LiteLLM.

CODEX Phase 1 complete: matter workspace primitives, runtime models (jobs/runs/steps/artifacts), Postgres runtime schema, provider-agnostic `ModelRouter`, `/document-viewer` endpoint, source citation anchors.

---

## Project Structure

```
themis/
  cli.py              # Typer CLI entry point
  graph.py            # LangGraph StateGraph definition
  state.py            # LexState TypedDict
  config.py           # LexConfig (all settings)
  nodes/              # intake, research, draft, cite, review, contract_review
  tools/              # kanoon, limitation, retriever, chunker, docx_writer, ...
  skills/             # bundled skill .md files
  memory/             # SOUL.md loader, matter memory, SQLite session store
  gateway/            # control_plane.py, telegram, voice
  runtime/            # jobs, worker, events, Postgres schema
  workspace/          # matter workspace models and repository
  ingestion/          # document ingestion, source anchors
  providers/          # ModelRouter over LiteLLM
tests/
docs/
```

---

## License

MIT — see [LICENSE](LICENSE).

---

*For the full architecture walkthrough, see [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md).*
