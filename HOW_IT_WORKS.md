# How Themis Works
### A Plain-English Guide for Lawyers and Developers

---

## Section 1: What Is Themis?

Themis is an open-source AI assistant built specifically for legal practice in India — and increasingly, for lawyers globally. The problem it solves is a simple but painful one: drafting a court-ready legal document (a writ petition, an injunction application, a legal notice) currently takes hours of manual research and writing. A lawyer must recall or look up the right statutes, find relevant Supreme Court and High Court judgments, check limitation periods, and then assemble everything into a properly structured document. One mistake — a wrong citation, an expired limitation period — can sink a client's case.

Themis automates the research-and-draft pipeline. A lawyer describes their matter in plain language ("I need to file a writ petition in Delhi HC for wrongful termination under Article 21"), and the agent asks targeted clarifying questions, searches Indian Kanoon for verified case law citations, checks the applicable limitation period, and produces a full court-ready draft with footnotes. The draft arrives as formatted text in the conversation and as a downloadable `.docx` file.

This project is a teaching build as much as a production tool. Every non-obvious code pattern carries an explanatory comment, and every design decision is documented. The goal is a codebase any lawyer-turned-developer, or developer new to legal tech, can understand and extend.

---

## Section 2: The Big Picture — How a Single Request Flows

Here is what happens from the moment a lawyer sends a message to the moment they receive a draft:

1. **Lawyer sends a message.** This can happen through a Telegram bot, a phone call (Twilio or browser microphone), or an HTTP REST/WebSocket call from a web browser. All of these are "gateways" — thin adapters that translate the incoming message into a standard format.

2. **The gateway forwards the message to the Control Plane.** The Control Plane is a single FastAPI backend (running on port 8000). Every gateway posts to the same backend. This means a lawyer can start a matter on Telegram and continue it on the web UI — the state is the same.

3. **The Control Plane authenticates and routes.** It checks the API token, identifies the firm and lawyer (`firm_id`, `user_id`), resolves the matter ID, and invokes the LangGraph agent.

4. **LangGraph runs the agent graph.** This is the brain. It is a structured flowchart where each step (called a "node") does one job: gather information, search case law, write the draft, verify citations, review the output. The graph walks through its nodes, updating a shared data structure called `LexState` at each step.

5. **The intake node asks clarifying questions.** If the lawyer's brief is incomplete, the agent generates structured questions (binary yes/no, multiple choice, or open text) and loops back until all required fields are filled.

6. **The research node searches Indian Kanoon.** Once intake is complete, the agent queries Indian Kanoon (India's largest free legal database) for relevant judgments, extracts citations, and checks the limitation period for the matter type.

7. **The draft node writes the document.** Using the lawyer's SOUL.md identity, the active skill file (which defines the document structure for the matter type), and the research findings, the LLM writes a full court-ready draft.

8. **The cite node verifies citations.** The draft's citations are cross-checked against the research findings using hybrid retrieval (keyword + semantic search). Unverified citations are flagged for the lawyer's review.

9. **The review node validates and exports.** The review node checks the draft for quality (length limits, empty content), annotates risks, and — if the lawyer requested a file — writes the draft to a `.docx` file.

10. **The output travels back through the Control Plane to the gateway.** The lawyer receives the draft as a formatted message in Telegram, a spoken response over voice, or streaming tokens in a web UI. The `.docx` is delivered as a file attachment.

11. **Memory is saved.** The matter's state is written to a per-matter `MEMORY.md` file, the session is logged in a searchable SQLite database, and the full LangGraph state is persisted to Postgres (if configured) for future resumption.

---

## Section 3: The Brain — LangGraph StateGraph

Think of LangGraph as a flowchart that the AI walks through step by step. Each box in the flowchart is a Python function (called a "node") that does one specific job. Arrows between boxes define which step comes next. Some arrows are conditional — the graph looks at the current data and decides which path to take, like a flowchart's diamond-shaped decision box.

The full graph flow is:

```
START
  ↓
[intake]  ← loops back to itself until all questions are answered
  ↓ (when complete)
[research]  ← searches Indian Kanoon, checks limitation period
  ↓
[draft]  ← writes the full legal document
  ↓
[cite]  ←  (optional: only if research found cases)
  ↓
[review]  ← quality check + .docx export
  ↓
END
```

There is also a separate branch: if the lawyer uploads a contract for review instead of requesting a new draft, the graph routes from `intake` directly to `contract_review` and then to `END`.

**What each node does:**

| Node | Job |
|---|---|
| `intake` | Reads the lawyer's brief, identifies what information is missing, generates clarifying questions, and loops until all required fields (matter type, parties, jurisdiction, purpose) are filled. |
| `research` | Builds a search query from the intake fields, calls the Indian Kanoon tool, extracts statutes, and runs a limitation period calculation. |
| `draft` | Assembles the system prompt from the SOUL.md identity, the active skill file, and research findings; calls the LLM; extracts the draft, a plain-English client summary, and risk annotations. |
| `cite` | Extracts citation strings (e.g. "AIR 1978 SC 597") from the draft, runs hybrid retrieval against research findings, marks each citation as verified or unverified. |
| `review` | Checks draft length against jurisdiction limits, flags unverified citations as warnings, and writes the `.docx` file if an output path was requested. |
| `contract_review` | Extracts text from an uploaded PDF contract, chunks it, asks the LLM to identify risky clauses, and returns a structured risk report. |

**LexState — the shared notepad.**

Every node reads from and writes to a single Python dictionary called `LexState`. Think of it as a notepad that gets passed around the table. Each node reads what it needs from the notepad, adds its results, and passes it on. No node stores anything internally. This is what makes the system inspectable, resumable, and testable — the entire state of a matter is always in one place.

Key fields in `LexState`:

- `user_input`, `matter_type`, `parties`, `jurisdiction`, `purpose` — what the lawyer told the agent
- `intake_complete` — the gate that controls the intake loop
- `research_findings`, `statutes_cited`, `limitation_analysis` — what the research node found
- `draft_output`, `risk_annotations`, `plain_english_summary` — what the draft node produced
- `citations_verified`, `unverified_citations` — what the cite node checked
- `docx_path` — where the review node saved the `.docx` file
- `messages` — the full conversation history (LangGraph appends to this automatically)
- `lawyer_soul`, `active_skill` — the lawyer's identity and the loaded skill file
- `firm_id`, `user_id`, `telegram_user_id`, `voice_session_id` — multi-tenant and gateway routing

---

## Section 4: The Gateways — How Lawyers Talk to Themis

All gateways funnel into one place: the **Control Plane**, a FastAPI backend that runs the LangGraph agent. Gateways are thin adapters — their only job is to translate an incoming message (a Telegram text, a phone call, an HTTP POST) into a standard API call to the control plane, and translate the response back to the appropriate format.

This design means matter state is shared. If a lawyer starts a matter on Telegram and later calls in via voice, the agent picks up exactly where it left off.

**Available gateways:**

| Gateway | How it works |
|---|---|
| **Telegram Bot** | The `python-telegram-bot` library handles incoming messages and callbacks. The bot presents clarifying questions as inline keyboard buttons (yes/no, multiple choice). When the draft is ready, the `.docx` is sent as a file attachment. Commands: `/start`, `/new`, `/status`, `/matters`, `/resume`, `/setup`, `/help`, `/reminder`. |
| **Voice — Browser WebSocket** | A browser opens a WebSocket connection to `/voice/ws/{session_id}`. The browser sends audio chunks (base64 encoded). The voice gateway runs Speech-to-Text (Whisper or Deepgram), steps through the LangGraph agent, converts the text response to speech (Google TTS or ElevenLabs), and streams audio back to the browser. No phone account needed. |
| **Voice — Twilio Phone** | Twilio calls `/voice/incoming` when a phone call arrives. The caller speaks their brief; Twilio sends the speech to `/voice/gather`. The gateway processes it through STT → LangGraph → TTS → TwiML `<Say>` response. A lawyer can dictate a matter brief over a phone call. |
| **REST API** | `POST /api/v1/matters/{matter_id}/message` — any HTTP client can send a message and receive the response. Used by WhatsApp webhooks, Slack integrations, and the web UI. |
| **WebSocket (Web UI)** | `ws://host:8000/ws/{matter_id}` — the web UI connects via WebSocket and receives LangGraph output tokens as they stream, enabling a ChatGPT-style streaming interface. |

The Control Plane also exposes:
- `GET /api/v1/matters` — list all matters for a lawyer
- `POST /api/v1/matters/{matter_id}/upload` — upload a contract PDF for review
- `GET /health` — health check

---

## Section 5: Memory — How Themis Remembers

Themis has four layers of memory, each serving a different purpose:

**Layer 1 — SOUL.md (permanent lawyer identity)**

Located at `~/.themis/SOUL.md`. This file is created during the first-run setup wizard (`lex setup`) and contains the lawyer's name, bar council enrollment number, preferred courts, drafting style preferences, and any custom instructions. Every time the agent drafts a document, it loads SOUL.md and injects it into the system prompt. This is how the agent knows to say "Brahm Sareen, Advocate" in the signature block without being told each time.

**Layer 2 — MEMORY.md per matter**

Located at `~/.themis/matters/{matter_id}/MEMORY.md`. Every time a matter session ends, the agent appends a snapshot of the matter state (type, parties, jurisdiction, research findings, draft status) to this file. On resumption, the agent reads MEMORY.md and picks up where it left off. This is human-readable — a lawyer can open it in any text editor.

**Layer 3 — SQLite sessions.db (searchable session history)**

Located at `~/.themis/sessions.db`. Every completed session is logged here with full-text search (SQLite FTS5). The lawyer can run `lex search "property dispute"` to find past matters, or `lex matter list` to see all matters in reverse chronological order. Reminders and deadlines are also stored here.

**Layer 4 — LangGraph Postgres Checkpointer (full agent state)**

When `DATABASE_URL` (Postgres) is configured, LangGraph saves a full snapshot of `LexState` after every node completes. This means:
- If the server crashes mid-draft, the matter resumes from the last checkpoint automatically.
- Human-in-the-loop: the agent can pause and wait for the lawyer's response, then resume exactly where it paused.
- Time-travel debugging: a developer can inspect any intermediate state of a matter.

In development mode without Postgres, LangGraph uses an in-memory `MemorySaver` — state lives only for the current process.

---

## Section 6: Skills — How the Agent Adapts to Matter Type

Different types of legal documents require completely different structures. A bail application has different mandatory sections than a writ petition. An injunction application needs different intake questions than a legal notice. The Skills system solves this without any code changes.

**Skills are Markdown files** stored in `themis/skills/` (bundled) and optionally in `~/.themis/skills/` (lawyer-custom overrides). Each file has a YAML frontmatter block at the top:

```yaml
---
name: civil_litigation
trigger_keywords: [plaint, injunction, civil suit, CPC, specific performance]
matter_types: [civil_suit, injunction_application, execution_petition]
---
```

The rest of the file is the skill content: mandatory intake checklist, document structure, drafting conventions, common pitfalls, and relevant statutes. This content is injected directly into the LLM's system prompt when the skill is active.

**Automatic skill selection:** The skills loader scans the trigger keywords against the lawyer's matter brief and the detected matter type. If the brief mentions "injunction," the civil litigation skill is loaded automatically. If it mentions "bail" or "custody," the criminal litigation skill is loaded. If no skill matches, the agent uses a generic drafting style.

**Lawyers can write their own skills.** Creating a new skill = creating a `.md` file with YAML frontmatter in `~/.themis/skills/`. A lawyer who handles arbitration cases can write an `arbitration.md` skill with their firm's preferred SIAC/DIAC structure. No Python required. User skills override bundled skills with the same name.

**Bundled skills include:** civil litigation, criminal litigation, legal notices, contract review, and starter skills for argument patterns, plain-English summaries, and drafting style.

---

## Section 7: Tools — What the Agent Can Look Up

Tools are functions the agent can call during the research phase. They self-register via a decorator — adding a new tool means dropping a new file into `themis/tools/` and decorating the function:

```python
@ToolRegistry.register(name="my_tool", description="...", schema={...})
def my_tool(...) -> dict:
    ...
```

The registry converts registered tools into LangChain format automatically, making them available for `bind_tools()` calls.

**Main tools:**

| Tool | What it does |
|---|---|
| **Indian Kanoon search** (`kanoon.py`) | Searches India's largest free legal database. Supports three backends: `stub` (mock data, works offline), `api` (direct HTTP with the lawyer's own API key), and `mcp` (delegates to the E-courts MCP server). Extracts case citations, judgment text, and URLs. |
| **Limitation calculator** (`limitation.py`) | Given a matter type and a cause-of-action date, calculates the applicable limitation period under the Limitation Act 1963, the filing deadline, and a risk level (expired / within 6 months / clear). |
| **Hybrid retriever** (`retriever.py`) | Given the research findings, builds a combined BM25 (keyword) + TF-IDF (semantic) index. Used by the cite node to verify whether a citation in the draft actually appears in the research corpus. The BM25 component is especially valuable for Indian citation strings like "AIR 1978 SC 597" where exact keyword matching matters. |
| **Qdrant vector store** (`retriever.py`) | When `LEX_QDRANT_ENABLED=true`, research findings are indexed into Qdrant (a vector database) for persistent, per-matter semantic retrieval that survives server restarts. |
| **Document chunker** (`chunker.py`) | Splits legal documents (text or PDF) into child chunks (256 tokens) and parent chunks (1024 tokens). Used for RAG — small chunks for precise retrieval, larger parent chunks fed to the LLM for context. |
| **LLM re-ranker** (`reranker.py`) | Optional: after retrieval, uses the LLM itself to score and re-rank passages by relevance to the query. Off by default to save API calls; enabled with `LEX_RERANKER_ENABLED=true`. |
| **RAPTOR summarizer** (`raptor_summarizer.py`) | Optional: clusters research findings and generates LLM summaries per cluster, building a hierarchy of summaries for complex multi-hop doctrinal queries. Off by default. |
| **Legal knowledge graph** (`legal_kg.py`) | Optional (GraphRAG): extracts legal entities (cases, statutes, courts, doctrines, parties) from research findings and builds a co-occurrence graph. Useful for finding indirect connections between cases. Off by default. |
| **DOCX writer** (`docx_writer.py`) | Converts the draft text (plain markdown) into a properly formatted `.docx` file with the lawyer's name in the footer, a matter ID, parties block, citations appendix, and court-appropriate font settings. |
| **Court fees calculator** (`court_fees.py`) | Calculates applicable court fees based on plaint valuation and matter type. |

---

## Section 8: The Tech Stack (for Developers)

| Component | Technology | Purpose |
|---|---|---|
| **Language** | Python 3.11+ | Core runtime |
| **Agent framework** | LangGraph ≥ 0.2 | StateGraph — all agent logic lives here |
| **LLM integration** | LangChain Core + LiteLLM | Calls Claude, GPT, Gemini, or local models via one interface |
| **Default LLM** | `claude-sonnet-4-6` (Anthropic) | The model that drafts documents |
| **API framework** | FastAPI + Uvicorn | Control plane (REST + WebSocket) |
| **CLI** | Typer + Rich | `lex draft "..."`, `lex setup`, `lex matter list` |
| **Configuration** | Pydantic Settings | `LexConfig` — all config in one class, reads from `.env` |
| **Persistent state** | Postgres + `langgraph-checkpoint-postgres` | Full LangGraph state per matter/thread |
| **Session history** | SQLite (built-in) + FTS5 | Searchable matter log, reminders |
| **Vector retrieval** | Qdrant + sentence-transformers | Semantic search over research findings (optional) |
| **Embeddings** | `all-MiniLM-L6-v2` | 22MB model, runs fully locally |
| **BM25 retrieval** | `rank-bm25` | Exact-keyword search — critical for Indian citations |
| **Document output** | `python-docx` | Generates `.docx` files from draft text |
| **PDF parsing** | `pdfplumber` | Extracts text from uploaded contract PDFs |
| **Telegram gateway** | `python-telegram-bot` | Bot with inline keyboards and file delivery |
| **Voice gateway — STT** | Whisper (OpenAI) or Deepgram | Speech-to-Text (opt-in extra) |
| **Voice gateway — TTS** | Google Cloud TTS or ElevenLabs | Text-to-Speech (opt-in extra) |
| **Voice gateway — Phone** | Twilio | Phone call integration (opt-in extra) |
| **Scheduling** | APScheduler | Proactive reminders (morning brief, hearing radar) |
| **Package manager** | uv | Fast Python package management |
| **Testing** | pytest + pytest-asyncio | 330+ tests, all async-aware |
| **Linting** | Ruff | Fast Python linter |
| **Type checking** | mypy | Static type analysis |

**Multi-provider LLM support:** LiteLLM acts as a universal adapter. Setting `LEX_MODEL=gpt-4o` and `LEX_MODEL_PROVIDER=openai` in `.env` switches the LLM without any code change. Local Ollama models are supported via `LEX_MODEL_BASE_URL=http://localhost:11434`.

---

## Section 9: What's Built vs What's Coming

### Built and Working (Phases 1–8B, 330+ tests passing)

- Full LangGraph pipeline: intake → research → draft → cite → review
- Contract review branch: upload a PDF, receive a structured risk report
- CLI: `lex draft`, `lex setup`, `lex matter list`, `lex matter show`, `lex search`, `lex reminder`
- Telegram gateway: inline keyboards, session persistence, `.docx` delivery, post-draft action menu, setup wizard
- Control plane: FastAPI with REST and WebSocket endpoints
- Voice gateway: browser WebSocket (no account needed) and Twilio phone gateway
- Memory system: SOUL.md, per-matter MEMORY.md, SQLite sessions with FTS5
- LangGraph Postgres checkpointer (production) with MemorySaver fallback (dev/tests)
- Hybrid RAG retrieval: BM25 + TF-IDF with optional Qdrant persistent vector store
- Skills system: 6 bundled skills, user override support, auto-selection by keyword
- Optional advanced retrieval: RAPTOR hierarchical summaries, GraphRAG entity extraction, LLM re-ranker
- `.docx` output with court-appropriate formatting
- Query expansion with Indian legal synonym dictionary
- Limitation period calculator
- Court fees calculator
- Multi-tenant identity fields (firm_id, user_id) in state and config

### Coming Next (Post-Phase 8B roadmap)

- **WhatsApp gateway** (Evolution API): thin adapter to control plane, identical to Telegram
- **Slack and Discord gateways**: `app_mention` and DM handling, thread-aware replies
- **Cron engine**: morning brief (daily matter digest), hearing radar (e-courts deadline scan), research queue (background research jobs)
- **Web UI pages** in lexanodes/: SOUL editor, firm registration, BYOK key management, matter dashboard
- **Telegram → Control Plane refactor**: Telegram currently calls `get_graph()` directly; roadmap moves it to POST to the control plane like all other gateways
- **LawyerSoul DB model hookup**: SOUL data currently lives in `~/.themis/SOUL.md`; the Prisma model exists but is not yet wired to the graph
- **Multi-tenant enforcement**: `multi_tenant` flag exists in config but is not yet enforced in routing

---

## Section 10: How to Run It Locally

Five commands to get from zero to a working draft:

```bash
# 1. Install all dependencies (uv is the package manager)
uv sync

# 2. Copy the environment template and add your Anthropic API key
cp .env.example .env
# Open .env and set: ANTHROPIC_API_KEY=sk-ant-...

# 3. Run the first-time setup wizard (creates ~/.themis/SOUL.md)
python -m themis.cli setup

# 4. Draft your first document
python -m themis.cli draft "I need to file a writ petition in Delhi HC challenging wrongful termination under Article 21"

# 5. Run the test suite to verify everything is working
pytest tests/ -v
```

**Optional extras:**

```bash
# Start the Telegram bot
python -m themis.cli gateway telegram

# Start the full control plane (REST + WebSocket + Voice)
python -m themis.gateway.control_plane

# Install voice gateway dependencies
uv sync --extra voice

# Enable Qdrant persistent vector retrieval (requires Docker)
docker run -p 6333:6333 qdrant/qdrant
# Then set LEX_QDRANT_ENABLED=true in .env
```

**Key environment variables:**

| Variable | Default | What it controls |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Your Claude API key |
| `LEX_MODEL` | `claude-sonnet-4-6` | Which LLM to use |
| `LEX_KANOON_BACKEND` | `stub` | `stub` (mock), `api` (real), `mcp` (E-courts MCP) |
| `DATABASE_URL` | (none) | Postgres for persistent LangGraph checkpoints |
| `TELEGRAM_BOT_TOKEN` | (none) | Telegram bot token |
| `LEX_QDRANT_ENABLED` | `false` | Enable persistent vector retrieval |
| `LEX_VOICE_ENABLED` | `false` | Enable the voice gateway |

All configuration lives in `themis/config.py` as `LexConfig`. Every field maps directly to a `.env` variable, making it straightforward to deploy with environment-specific settings without touching code.

---

*This document covers the codebase as of Phase 8B (May 2026). For the full build specification and phase-by-phase implementation details, see `THEMIS_CLAUDE_CODE_BRIEF.md`. For the post-Phase 8B roadmap, see `POST_PHASE8B_IMPLEMENTATION_PLAN.md`.*
