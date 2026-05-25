# LexAgent Revamp — Exhaustive Implementation Plan

> Generated: 2026-05-24. Do not edit manually — this is the authoritative implementation blueprint.
> Phases must be executed in order. Each phase's success criteria must pass before the next begins.

---

## 1. New Dependency List

All additions go into `pyproject.toml`. Existing deps remain unchanged.

### Core dependencies (add to `[project] dependencies`)

| Package | Version Pin | Reason |
|---|---|---|
| `mem0ai` | `>=0.1.29` | Self-hosted mem0 for three-layer memory (user/agent/session), replaces flat SOUL.md + MATTER.md |
| `llama-parse` | `>=0.4.0` | LlamaParse SDK for PDF/DOCX/image/handwritten OCR ingestion pipeline |
| `tavily-python` | `>=0.3.0` | Tavily web search for statutory texts, gazette notifications, law commission reports |
| `httpx` | `>=0.27` | Async HTTP client for Indian Kanoon REST API (`api.indiankanoon.org`) |
| `python-jose[cryptography]` | `>=3.3.0` | JWT token signing and verification for per-firm/per-lawyer auth in control plane |
| `cryptography` | `>=42.0` | AES-256 encryption at rest for Qdrant payload fields (DPDP compliance) |
| `langchain-mcp-adapters` | `>=0.1.0` | LangChain-native MCP tool adapter so eCourts MCP tools register into ToolRegistry |
| `mcp` | `>=1.0.0` | Model Context Protocol Python SDK (required by langchain-mcp-adapters) |
| `openapi-spec-validator` | `>=0.7.0` | Validate user-pasted OpenAPI specs for third-party REST connector introspection |
| `jsonschema` | `>=4.21` | Schema validation for connector tool definitions and skill YAML frontmatter |
| `babel` | `>=2.14` | Language/locale detection for translation feature; also used for date localisation |
| `deep-translator` | `>=1.11` | Hindi↔English translation fallback (no API key needed, uses Google Translate backend) |
| `aiosmtplib` | `>=3.0` | Async SMTP for JARVIS email tool |
| `aiofiles` | `>=23.0` | Async file I/O for bundle generator and document downloads |
| `structlog` | `>=24.0` | Structured JSON audit logging for DPDP compliance (replaces plain `logging`) |
| `slowapi` | `>=0.1.9` | Rate limiting middleware for FastAPI control plane (per-firm request throttling) |
| `pandas` | `>=2.2` | CSV/Excel ingestion in KB file upload pipeline |
| `openpyxl` | `>=3.1` | Excel `.xlsx` reading (pandas backend) |
| `Pillow` | `>=10.0` | Image preprocessing before LlamaParse OCR (JPEG/PNG normalization) |

### Optional extras (add new `[project.optional-dependencies]` groups)

```toml
[project.optional-dependencies]
kb = [
    "llama-parse>=0.4.0",
    "pandas>=2.2",
    "openpyxl>=3.1",
    "Pillow>=10.0",
    "aiofiles>=23.0",
]

translate = [
    "deep-translator>=1.11",
    "babel>=2.14",
]

connectors = [
    "langchain-mcp-adapters>=0.1.0",
    "mcp>=1.0.0",
    "openapi-spec-validator>=0.7.0",
]

security = [
    "cryptography>=42.0",
    "python-jose[cryptography]>=3.3.0",
    "structlog>=24.0",
]

jarvis = [
    "aiosmtplib>=3.0",
    "slowapi>=0.1.9",
]
```

Dev dependencies to add:
- `respx>=0.21` — mock `httpx` async calls in tests for Kanoon API
- `pytest-mock>=3.12` — general mock support for new modules
- `freezegun>=1.4` — freeze time for calendar/deadline tests

---

## 2. New/Changed Files Map

### New files to create

| File Path | What and Why |
|---|---|
| `lexagent/tools/kanoon_api.py` | Indian Kanoon REST API client (`api.indiankanoon.org`). Async `httpx`-based. Methods: `search(query, pagenum)` → list of `{docid, title, snippet}`, and `fetch_doc(docid)` → full text. Returns `None` on broken text so caller triggers Playwright fallback. |
| `lexagent/tools/kanoon_fallback.py` | Renamed and isolated Playwright scraper (current `kanoon.py` content, stripped of search logic). Exposes `fetch_doc_playwright(url) -> str`. Used only when API returns broken text for a specific docid. |
| `lexagent/tools/tavily_search.py` | Tavily web search tool. Async `search(query, max_results) -> list[dict]`. Returns `{title, url, content, score}`. Registered in ToolRegistry with `@ToolRegistry.register("web_search", ...)`. |
| `lexagent/tools/ecourts_mcp.py` | eCourts MCP tool adapter. Uses `langchain-mcp-adapters` to wrap `mcp__claude_ai_E-courts__*` tools into LangChain `StructuredTool` objects. Exposes `get_ecourts_tools() -> list[StructuredTool]`. Toggle-controlled via `enable_ecourts` config. |
| `lexagent/nodes/react_research.py` | New ReAct research agent. Full tool-use loop with `plan → search → fetch → evaluate → loop` pattern. Uses LangGraph `create_react_agent` with tool set [kanoon_api_search, kanoon_fetch_doc, web_search, check_limitation, ecourts_tools...]. **Replaces** `lexagent/nodes/research.py` run logic. CITATION ENFORCEMENT GATE lives here — drops any finding without `{title, citation, doc_excerpt, url}` before returning. Verified judgments auto-downloaded to `~/.lexagent/judgments/{doc_id}.txt` and indexed into Qdrant `{firm_id}_judgments`. |
| `lexagent/memory/mem0_client.py` | mem0 self-hosted client wrapper. Wraps `mem0ai.Memory` configured with Qdrant vector backend. Methods: `add(text, user_id, agent_id, metadata)`, `search(query, user_id, agent_id, limit)`, `get_user_memories(user_id)`, `get_agent_memories(matter_id)`. Replaces `soul.py` read/write logic for user preferences. |
| `lexagent/memory/lawyer_memory.py` | High-level memory facade. `load_lawyer_profile(user_id, firm_id) -> dict`, `save_lawyer_preference(user_id, firm_id, key, value)`, `load_matter_context(matter_id) -> dict`, `save_feedback(matter_id, diff, weight: float)`. Replaces `soul.py` and `matter_memory.py` usage. |
| `lexagent/kb/ingestion.py` | KB ingestion pipeline. `ingest_file(file_path, collection_name, metadata) -> int` — dispatches to the right parser by extension (PDF→LlamaParse, DOCX→LlamaParse, JPEG/PNG→LlamaParse vision OCR, CSV/Excel→pandas, audio→Whisper STT). Chunks output, upserts into Qdrant collection. |
| `lexagent/kb/collections.py` | Qdrant collection manager. `ensure_collection(name, dim, distance)`, `get_firm_kb_collection(firm_id)`, `get_matter_collection(matter_id)`, `get_judgments_collection(firm_id)`. Centralizes all collection naming conventions. |
| `lexagent/nodes/parallel_orchestrator.py` | Parallel agent orchestrator. Implements Mode 1 (JARVIS auto-split), Mode 2 (slash command trigger), Mode 3 (LLM Council). `run_parallel_research(state, sub_queries: list[str]) -> list[dict]` launches isolated `StateGraph.invoke()` calls via `asyncio.gather()`. LLM Council mode uses adversarial debate pattern: 3+ agents with different models, each critiques others' citations, converges when 2/3 agree. |
| `lexagent/nodes/bundle_generator.py` | Filing bundle generator node. `run(state) -> dict`. Reads `bundle_template_name` from state, loads template from mem0 agent memory, identifies missing documents, asks proactively, drafts agent-generated docs via draft node, assembles zip with numbered filenames. Pre-built NI Act S.138 template hardcoded as fallback. |
| `lexagent/nodes/translator.py` | Translation node. `run(state) -> dict`. Two modes: `reading` (direct LLM call) and `filing` (structured legal terminology preservation + lawyer review gate). Supports Hindi↔English initially. Inline vs side-by-side preference stored in mem0 user memory. |
| `lexagent/nodes/skill_creator.py` | Skill creator agent. `run(state) -> dict`. Generates `.md` skill files with YAML frontmatter from lawyer instruction or JARVIS-observed patterns. Tracks skill quality scores via feedback loop. Skills stored in `~/.lexagent/skills/` and shared across all agents. |
| `lexagent/nodes/jarvis_router.py` | JARVIS intent classifier. `classify_intent(user_input) -> str` maps every message to one of `{draft|research|calendar|status|memory_query|reminder|mail|council|kb_upload|translate|bundle|skill_create}`. Runs as the first step in the control plane before routing to the graph. |
| `lexagent/connectors/mcp_connector.py` | Third-party MCP connector. `register_mcp_server(server_url, firm_id)` — connects to MCP server, introspects tools, registers each as a LangChain `StructuredTool` in ToolRegistry under the firm's namespace. Stored in `connectors.json` under `~/.lexagent/firms/{firm_id}/`. |
| `lexagent/connectors/rest_connector.py` | Third-party REST API connector. `register_rest_api(openapi_url_or_spec, firm_id)` — fetches/validates OpenAPI spec, generates LangChain tools for each endpoint, registers in ToolRegistry. |
| `lexagent/connectors/connector_store.py` | Persistence layer for connectors. Reads/writes `~/.lexagent/firms/{firm_id}/connectors.json`. `list_connectors(firm_id)`, `save_connector(firm_id, connector_def)`, `delete_connector(firm_id, name)`. |
| `lexagent/security/encryption.py` | AES-256-GCM encryption helpers for Qdrant payload fields. `encrypt_payload(data: dict, key: bytes) -> dict`, `decrypt_payload(data: dict, key: bytes) -> dict`. Key derived from `LEX_ENCRYPTION_KEY` env var via PBKDF2. |
| `lexagent/security/audit.py` | DPDP-compliant audit logger. Wraps `structlog`. `log_access(user_id, firm_id, resource_type, resource_id, action)`, `log_generation(user_id, firm_id, matter_id, doc_type)`. Writes to `~/.lexagent/audit.jsonl` and optionally Postgres. |
| `lexagent/security/jwt_auth.py` | JWT token issuance and verification. `create_token(firm_id, user_id, role) -> str`, `decode_token(token) -> dict`. Replaces the current naive bearer-token string comparison in `control_plane.py`. |
| `lexagent/gateway/intent_router.py` | Maps intents from `jarvis_router.py` to the correct graph or direct action. `route_intent(intent, state) -> str` returns node name or action. Decouples intent routing from graph conditional edges. |
| `lexagent/skills/bundle_templates/ni_act_138.yaml` | Pre-built NI Act Section 138 bundle template. YAML defining 9-document order: 4 agent-drafted, 5 lawyer-uploaded. Each entry has `{slot, name, source: agent\|lawyer, draft_type, required: bool}`. |
| `lexagent/skills/setup_wizard.py` | New KB mode setup wizard. Asks firm type (enterprise/individual/small office), configures KB mode, sets Qdrant collections, writes `~/.lexagent/firms/{firm_id}/config.json`. |
| `tests/test_kanoon_api.py` | Tests for Kanoon REST API client (mock httpx with `respx`). |
| `tests/test_react_research.py` | Tests for the new ReAct research node. |
| `tests/test_mem0_client.py` | Tests for mem0 client wrapper (mock mem0 SDK). |
| `tests/test_kb_ingestion.py` | Tests for KB ingestion pipeline. |
| `tests/test_bundle_generator.py` | Tests for filing bundle generator. |
| `tests/test_translator.py` | Tests for translation node. |
| `tests/test_skill_creator.py` | Tests for skill creator agent. |
| `tests/test_connectors.py` | Tests for MCP and REST connector registration. |
| `tests/test_parallel_orchestrator.py` | Tests for parallel agent orchestrator. |
| `tests/test_jwt_auth.py` | Tests for JWT token create/decode. |
| `tests/test_audit.py` | Tests for audit logger output format. |
| `docker-compose.yml` | Services: `qdrant`, `mem0`, `postgres`, `lexagent-control-plane`. |
| `Dockerfile` | Python 3.11-slim, uv, all-extras install, non-root `lexagent` user. |
| `.dockerignore` | Excludes `.env`, `__pycache__`, `.pytest_cache`, etc. |

### Significantly changed existing files

| File Path | What Changes |
|---|---|
| `lexagent/nodes/research.py` | `run()` replaced: calls ReAct agent from `react_research.py`. CITATION ENFORCEMENT GATE applied before writing to state. |
| `lexagent/tools/kanoon.py` | Rename to `kanoon_fallback.py`; keep `kanoon.py` as backwards-compat shim during transition. |
| `lexagent/tools/registry.py` | Add `register_langchain_tool(tool)`, `get_firm_tools(firm_id)`, `unregister(name)` for dynamic MCP/REST connector registration. |
| `lexagent/state.py` | Add ~30 new Optional fields (see Section 3). |
| `lexagent/config.py` | Add ~30 new config keys (see Section 4). |
| `lexagent/gateway/control_plane.py` | Add JWT auth, intent routing, rate limiting, audit logging, new endpoints for KB upload, connectors, translate, bundle, traces. |
| `lexagent/memory/soul.py` | Route reads/writes through `lawyer_memory.py` mem0 facade. File fallback when mem0 disabled. |
| `lexagent/graph.py` | Add nodes: `parallel_research`, `bundle_generator`, `translator`, `skill_creator`. Add conditional edges. |
| `lexagent/nodes/cite.py` | Citation gate strengthened: `doc_excerpt` required. Integrate with mem0 for past verified citations. |
| `lexagent/nodes/draft.py` | Read lawyer profile from mem0 user layer. Persist matter context to mem0 on completion. |
| `lexagent/cli.py` | Add commands: `lex translate`, `lex bundle`, `lex connector add/list/remove`, `lex skill create`, `lex memory search`, `lex setup-kb`. |

---

## 3. LexState Changes

Add the following fields to `LexState` TypedDict in `lexagent/state.py`:

```python
# --- Research ReAct Agent (Phase R1) ---
research_tool_toggles: Optional[dict]        # {kanoon: bool, ecourts: bool, web_search: bool}
research_agent_trace: Optional[List[dict]]   # [{step, tool, input, output, timestamp}]
citation_gate_dropped: Optional[List[dict]]  # Findings dropped by citation enforcement gate

# --- KB + Memory (Phase R2A/R2B) ---
kb_collection: Optional[str]                 # Active Qdrant collection name for this matter
mem0_user_id: Optional[str]                  # mem0 user-layer ID
mem0_agent_id: Optional[str]                 # mem0 agent-layer ID (same as matter_id)
lawyer_profile: Optional[dict]               # Loaded from mem0 user layer
matter_context: Optional[dict]               # Loaded from mem0 agent layer
feedback_pending: Optional[bool]             # True after draft delivery
feedback_rating: Optional[int]               # 1-5 rating from lawyer post-delivery
feedback_diff: Optional[str]                 # Lawyer edits diff for mem0 storage

# --- File Upload + KB Ingestion (Phase R2C) ---
uploaded_files: Optional[List[dict]]         # [{filename, path, collection, chunks_indexed, status}]
ingestion_status: Optional[str]              # "pending" | "indexing" | "complete" | "failed"

# --- Parallel Agents (Phase R3) ---
parallel_mode: Optional[str]                 # "orchestrator" | "slash" | "council"
subagent_results: Optional[List[dict]]       # [{agent_id, model, findings, quality_score}]
council_convergence: Optional[bool]          # True when 2/3 council agents agree
council_quality_score: Optional[float]       # 0-1 quality score for future task similarity
subagent_traces: Optional[dict]              # {agent_id: [trace_steps]}

# --- Filing Bundle (Phase R4) ---
bundle_template_name: Optional[str]          # e.g. "ni_act_138" or custom name
bundle_slots: Optional[List[dict]]           # [{slot, name, source, status, file_path, draft_text}]
bundle_zip_path: Optional[str]               # Path to generated zip file
bundle_missing_docs: Optional[List[str]]     # Slot names awaiting lawyer upload

# --- Translation (Phase R5/R6) ---
translation_mode: Optional[str]              # "reading" | "filing"
translation_source_lang: Optional[str]       # BCP-47 (e.g. "hi", "en")
translation_target_lang: Optional[str]       # BCP-47
translated_output: Optional[str]             # Full translated text
translation_display_mode: Optional[str]      # "inline" | "side_by_side"

# --- Skill Creator (Phase R5) ---
skill_create_request: Optional[str]          # Natural language description of skill to create
created_skill_path: Optional[str]            # Path to generated .md skill file
skill_quality_history: Optional[List[dict]]  # [{skill_name, matter_id, rating}]

# --- JARVIS Intent Routing (Phase R7) ---
jarvis_intent: Optional[str]                 # Classified intent enum value
pending_approval: Optional[bool]             # High-stakes action requires lawyer confirmation
approval_prompt: Optional[str]               # Message shown requesting approval

# --- Connectors (Phase R5) ---
active_connectors: Optional[List[str]]       # Tool names from registered connectors active for this matter

# --- Security (Phase R8) ---
audit_logged: Optional[bool]                 # Prevents double-logging
```

---

## 4. LexConfig Changes (key additions by phase)

```python
# Phase R1: Research
kanoon_api_url: str = Field("https://api.indiankanoon.org", ...)
kanoon_fallback_playwright: bool = Field(True, ...)
tavily_api_key: Optional[str] = Field(None, ...)
tavily_enabled: bool = Field(False, ...)
ecourts_mcp_enabled: bool = Field(False, ...)
react_research_max_iterations: int = Field(5, ...)
judgments_cache_dir: str = Field("~/.lexagent/judgments", ...)

# Phase R2A: Qdrant
qdrant_encryption_key: Optional[str] = Field(None, ...)
qdrant_judgments_collection_suffix: str = Field("judgments", ...)
qdrant_kb_collection_suffix: str = Field("kb", ...)
qdrant_matter_collection_suffix: str = Field("docs", ...)

# Phase R2B: mem0
mem0_enabled: bool = Field(False, ...)
mem0_server_url: Optional[str] = Field(None, ...)
mem0_api_key: Optional[str] = Field(None, ...)

# Phase R2C: File Ingestion
llama_parse_api_key: Optional[str] = Field(None, ...)
llama_parse_enabled: bool = Field(False, ...)
kb_max_file_size_mb: int = Field(50, ...)
kb_mode: str = Field("individual", ...)  # "enterprise" | "individual" | "small_office"

# Phase R3: Parallel Agents
parallel_agents_enabled: bool = Field(False, ...)
council_min_agents: int = Field(3, ...)
council_models: str = Field("claude-sonnet-4-6,gpt-4o,gemini-1.5-pro", ...)

# Phase R4: Filing Bundle
bundle_output_dir: str = Field("~/.lexagent/bundles", ...)
bundle_templates_dir: str = Field("~/.lexagent/bundle_templates", ...)

# Phase R6: Translation
translation_enabled: bool = Field(False, ...)
translation_default_source: str = Field("auto", ...)
translation_default_target: str = Field("en", ...)

# Phase R5: Skill Creator + Connectors
skill_auto_suggest: bool = Field(True, ...)
connectors_file: str = Field("~/.lexagent/connectors.json", ...)

# Phase R7: JARVIS
jarvis_mode_enabled: bool = Field(False, ...)
jarvis_require_approval: bool = Field(True, ...)
smtp_host: Optional[str] = Field(None, ...)
smtp_port: int = Field(587, ...)
smtp_username: Optional[str] = Field(None, ...)
smtp_password: Optional[str] = Field(None, ...)
smtp_from_address: Optional[str] = Field(None, ...)

# Phase R8: Security / DPDP
audit_log_path: str = Field("~/.lexagent/audit.jsonl", ...)
audit_log_postgres: bool = Field(False, ...)
dpdp_data_residency: str = Field("IN", ...)
secrets_backend: str = Field("env", ...)
jwt_secret_key: Optional[str] = Field(None, ...)
jwt_algorithm: str = Field("HS256", ...)
jwt_expiry_hours: int = Field(24, ...)
rate_limit_per_firm_per_minute: int = Field(60, ...)
```

---

## 5. Docker Compose

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: lexagent
      POSTGRES_USER: lexagent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-lexagent_dev}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lexagent"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:v1.9.4
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
      - "6334:6334"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY:-}
      QDRANT__STORAGE__ON_DISK_PAYLOAD: "true"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5

  mem0:
    image: mem0ai/mem0:latest
    depends_on:
      qdrant:
        condition: service_healthy
    environment:
      MEM0_VECTOR_STORE_PROVIDER: qdrant
      MEM0_QDRANT_URL: http://qdrant:6333
      MEM0_QDRANT_API_KEY: ${QDRANT_API_KEY:-}
      MEM0_EMBEDDING_MODEL: sentence-transformers/all-MiniLM-L6-v2
    env_file:
      - .env
    volumes:
      - mem0_data:/app/data
    ports:
      - "8888:8888"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8888/health"]
      interval: 15s
      timeout: 5s
      retries: 5

  lexagent:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      mem0:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://lexagent:${POSTGRES_PASSWORD:-lexagent_dev}@postgres:5432/lexagent
      QDRANT_URL: http://qdrant:6333
      MEM0_SERVER_URL: http://mem0:8888
      LEX_QDRANT_ENABLED: "true"
      LEX_MEM0_ENABLED: "true"
    env_file:
      - .env
    volumes:
      - lexagent_data:/root/.lexagent
    ports:
      - "8000:8000"
    command: uvicorn lexagent.gateway.control_plane:app --host 0.0.0.0 --port 8000

volumes:
  postgres_data:
  qdrant_data:
  mem0_data:
  lexagent_data:
```

---

## 6. Phase-by-Phase Implementation Order

### Phase R1: Research Overhaul
**Goal:** Replace fragile Playwright scraper with real ReAct research agent with tool-use loop.

**Build:**
1. `kanoon_api.py` — Kanoon REST API client, `search()` + `fetch_doc()`, returns `None` on broken text
2. `kanoon_fallback.py` — isolated Playwright scraper, only `fetch_doc_playwright(url) -> str`
3. `tavily_search.py` — Tavily web search tool, registered in ToolRegistry
4. `ecourts_mcp.py` — eCourts MCP adapter via `langchain-mcp-adapters`
5. `react_research.py` — ReAct agent with `create_react_agent`, CITATION ENFORCEMENT GATE (drops findings without `{title, citation, doc_excerpt, url}`)
6. Update `research.py` to invoke ReAct agent
7. Judgment auto-download to `~/.lexagent/judgments/{docid}.txt` + Qdrant indexing

**Files:** CREATE kanoon_api.py, kanoon_fallback.py, tavily_search.py, ecourts_mcp.py, react_research.py. CHANGE research.py, kanoon.py, config.py, state.py.

**Tests:** test_kanoon_api.py (mock httpx with respx), test_react_research.py (citation gate).

**Success criteria:**
- All test_kanoon.py tests pass
- `lex draft "cheque bounce S.138"` produces findings with `doc_excerpt` in every item
- Citation gate drops malformed findings

**Unblocks:** R2A (Qdrant judgment indexing), R3 (parallelizing real research tools)

---

### Phase R2A: Qdrant + KB Infrastructure
**Goal:** Real persistent vector storage; payload encryption for DPDP.

**Build:**
1. `kb/collections.py` — collection naming conventions, `ensure_collection()`
2. Upgrade `retriever.py` to use collection manager
3. `security/encryption.py` — AES-256-GCM, opt-in via `qdrant_encryption_key`
4. Wire encryption into all Qdrant upsert/fetch paths
5. Add `docker-compose.yml` with Qdrant service

**Success criteria:**
- `docker compose up qdrant` passes healthcheck
- Research findings indexed and retrievable across restarts
- Encrypted payloads show ciphertext in Qdrant storage

---

### Phase R2B: mem0 Integration
**Goal:** Three-layer persistent memory replacing flat files.

**Build:**
1. `memory/mem0_client.py` — mem0 SDK wrapper, three layers (user/agent/session)
2. `memory/lawyer_memory.py` — facade: `load_lawyer_profile`, `save_lawyer_preference`, `load_matter_context`, `save_feedback`
3. Update `soul.py`, `draft.py`, `intake.py` to route through facade
4. Feedback loop: `save_feedback(matter_id, diff, weight)` after draft rating
5. KB mode setup wizard (`skills/setup_wizard.py`)
6. Add mem0 Docker service

**Success criteria:**
- `LEX_MEM0_ENABLED=true` → lawyer profile reads from mem0, not SOUL.md
- `LEX_MEM0_ENABLED=false` → falls back to SOUL.md (all existing tests still pass)
- Feedback from rated matter influences next similar matter's draft

---

### Phase R2C: File Upload API + LlamaParse Ingestion
**Goal:** Full file ingestion pipeline for KB building.

**Build:**
1. `kb/ingestion.py` — dispatcher by file type: PDF/DOCX/images→LlamaParse (fallback pdfplumber), CSV/Excel→pandas, audio→Whisper
2. `/remember` chat command → ingest to matter KB
3. Extend control plane upload endpoint with collection routing
4. CLI `lex kb upload {file} --matter {matter_id}`

**Success criteria:**
- Uploading a 10-page PDF → chunks appear in Qdrant `{matter_id}_docs`
- `/remember This court requires original stamps` → retrievable via semantic search
- File size limit enforced; budget guard for LlamaParse pages

---

### Phase R3: Parallel Agents + LLM Council
**Goal:** Three modes of parallel agent execution.

**Build:**
1. `nodes/parallel_orchestrator.py`:
   - Mode 1: JARVIS auto-split via `asyncio.gather()` with isolated `StateGraph.invoke()`
   - Mode 2: Slash commands `/council`, `/parallel-research`, `/split-draft`
   - Mode 3: LLM Council — 3+ agents, different models, adversarial debate, convergence when 2/3 agree
2. Subagent traces stored in `state["subagent_traces"]`
3. Quality score stored in mem0 on council convergence
4. Graph wiring: `parallel_research` node, conditional edges

**Success criteria:**
- `lex draft "cheque bounce" --mode=council` launches 3 agents, merges findings
- `/show-traces {matter_id}` returns trace dict with 3 subagent keys
- One agent failure does not cancel other agents

---

### Phase R4: Filing Bundle Generator
**Goal:** Court-ready bundle assembly with proactive document requests.

**Build:**
1. `skills/bundle_templates/ni_act_138.yaml` — 9-slot NI Act S.138 template
2. `nodes/bundle_generator.py` — reads template, checks slots, proactively asks for missing docs, drafts agent slots, assembles zip
3. Custom templates via mem0 (lawyer defines order, stored as `bundle_templates` in agent memory)
4. CLI `lex bundle {matter_id}` + control plane endpoint

**NI Act S.138 Template (slot order):**
1. Memo of Parties — agent-drafted
2. Complaint under Section 138 — agent-drafted
3. List of Documents — agent-generated
4. Copy of transaction/payment proof — lawyer-uploaded
5. Original cheque copy — lawyer-uploaded
6. Bank return memo copy — lawyer-uploaded
7. Legal notice copy — lawyer-uploaded
8. Speed post tracking receipt — lawyer-uploaded
9. Vakalatnama — agent-drafted

**Success criteria:**
- `lex bundle M-001 --template=ni_act_138` → zip with 9 numbered files
- Agent asks proactively for missing lawyer-uploaded slots
- Custom lawyer-defined template persists across restarts

---

### Phase R5: Skill Creator + Third-Party Connectors
**Goal:** Lawyers create skills; connect any API or MCP server.

**Build:**
1. `nodes/skill_creator.py` — generates `.md` skill files from NL instruction or JARVIS-observed patterns. Tracks quality via feedback.
2. JARVIS auto-suggest: pattern observation fires after 3 identical workflow triggers
3. `connectors/mcp_connector.py` — paste MCP server URL → tools registered in ToolRegistry under firm namespace
4. `connectors/rest_connector.py` — OpenAPI spec URL → tools generated and registered
5. `connectors/connector_store.py` — JSON persistence
6. ToolRegistry extensions: `register_langchain_tool`, `get_firm_tools`, `unregister`
7. CLI `lex connector add/list/remove` + `lex skill create`

**Success criteria:**
- `lex skill create "Always add 3 precedents for injunctions"` → writes skill file
- `lex connector add https://example.com/openapi.json` → tools appear in `lex connector list`
- Registered connector tools available in research ReAct loop
- Auto-suggest fires after 3 identical matter type + doc type + jurisdiction combos

---

### Phase R6: Translation
**Goal:** Hindi↔English translation for all document types.

**Build:**
1. `nodes/translator.py`:
   - `reading` mode: direct LLM call, fast
   - `filing` mode: structured output, legal term preservation, lawyer review gate → `pending_approval = True`
2. Display preference (inline/side-by-side) stored in mem0 user layer
3. CLI `lex translate {file} --to=hi --mode=reading`
4. Control plane `POST /api/v1/translate`

**Success criteria:**
- `lex translate judgment.pdf --to=hi --mode=reading` produces Hindi text in <10s
- Filing mode sets `pending_approval = True`
- Display preference remembered across sessions

---

### Phase R7: JARVIS Full Assistant Mode
**Goal:** Proactive ambient assistant across all intents.

**Build:**
1. `nodes/jarvis_router.py` — LLM-based intent classifier with structured output
2. `gateway/intent_router.py` — maps intent → `workflow_mode` → graph entry
3. Calendar/deadline integration — APScheduler, matter memory for hearing dates, 7am daily digest
4. Email tool — `aiosmtplib`, guarded by `jarvis_require_approval`
5. `/search-memory` command — NL queries against mem0
6. Meeting notes: STT → summarize → `save_to_matter_kb()`
7. Proactive reminders via Telegram/WhatsApp
8. "Approval gate" for high-stakes actions

**Success criteria:**
- Every Telegram message classified before graph invocation
- `/search-memory limitation period for cheque bounce` returns relevant memories
- Daily digest lists matters with hearings in next 7 days
- Email blocked until lawyer confirms when `jarvis_require_approval = True`

---

### Phase R8: DPDP Compliance Hardening + Docker Production
**Goal:** Production-ready security, audit trails, data isolation.

**Build:**
1. `security/jwt_auth.py` — `create_token`, `decode_token` replacing naive bearer check
2. `security/audit.py` — structlog JSON audit logging, `log_access`, `log_generation`
3. Rate limiting via `slowapi` — per-firm throttling
4. Qdrant payload encryption verification across all upsert/fetch paths
5. Data isolation audit — all Qdrant queries include `firm_id` filter
6. `Dockerfile` — Python 3.11-slim, non-root user, uv all-extras
7. `.dockerignore` — excludes .env, __pycache__
8. Data deletion endpoint `DELETE /api/v1/matters/{matter_id}/data` (DPDP right-to-erasure)

**Success criteria:**
- `docker compose up` → all healthchecks pass within 60s
- JWT required for all endpoints except `/health`
- Audit log written for every matter message and document upload
- Cross-tenant Qdrant query returns zero results

---

## 7. CRG Update Instructions

After all phases complete, run these in order:

1. `detect_changes_tool` — identify modified graph nodes
2. `build_or_update_graph_tool` — `{"repo_path": "/Users/anshoosareen/Lexagent", "force_rebuild": true}`
3. `embed_graph_tool` — `{"repo_path": "/Users/anshoosareen/Lexagent"}`
4. `run_postprocess_tool` — `{"repo_path": "/Users/anshoosareen/Lexagent"}`
5. `generate_wiki_tool` — `{"repo_path": "/Users/anshoosareen/Lexagent", "overwrite": true}`

---

## 8. Breaking Changes

| Test File | Will Break? | Reason | Action |
|---|---|---|---|
| `test_kanoon.py` | YES — already failing | `search_and_fetch` import path changes | Rewrite against `kanoon_api.py` with `respx` mocks |
| `test_research.py` | YES | `research_findings` shape changes — requires `doc_excerpt` | Update fixture data and assertions |
| `test_memory.py` | PARTIAL | `load_soul`/`save_soul` fallback path changes | Add mem0-enabled test variants |
| `test_registry.py` | PARTIAL | Tool count no longer fixed at module-load time | Replace count assertions with named assertions |
| `test_control_plane.py` | YES | JWT auth replaces naive bearer string | Rewrite with JWT or `api_secret_key = None` mode |
| `test_retriever.py` | PARTIAL | Collection manager + encryption hooks in upsert/fetch | Add `qdrant_encryption_key=None` in test config |
| `test_cite.py` | PARTIAL | `doc_excerpt` now required; gate drops findings | Update fixture data to include `doc_excerpt` |
| `test_state.py` | YES | ~30 new TypedDict fields | Replace set-equality assertions with `in` checks |
| All others | NO | Isolated unit tests for unchanged tools/nodes | No action needed |

**Summary:** ~15 tests fully break (rewrite), ~25 partially break (extend), ~239 unaffected.

---

## 9. Risk Register

### Risk 1: Indian Kanoon API returns broken judgment text
**Mitigation:** `_is_broken_text()` heuristic (length < 200 chars, or `<html>` in response). Cache raw API responses in `~/.lexagent/judgments/{docid}_raw.json`. Test with 50 real docids before shipping R1.

### Risk 2: mem0 self-hosted Docker image stability
**Mitigation:** `MemoryBackend` abstract base class with `Mem0Backend` and `FileBackend`. Pin Docker image to specific version tag. All memory tests use mock backend — no running mem0 server required.

### Risk 3: eCourts MCP adapter authentication unknown
**Mitigation:** `ecourts_mcp_enabled` defaults to `False`. Implement `eCourtsDirectClient` HTTP fallback. Stub implementation for all test coverage. Document as "requires lawyer to configure MCP server URL."

### Risk 4: LlamaParse cost and rate limits at scale
**Mitigation:** `llama_parse_enabled` defaults to `False`. LlamaParse only activated for scanned PDFs and images. `kb_llama_parse_monthly_page_budget` config key enforces usage cap with pdfplumber fallback.

### Risk 5: Qdrant vector data not encrypted (DPDP gap)
**Mitigation:** Document in `DPDP_COMPLIANCE.md` that embeddings are pseudonymized. Recommend encrypted filesystem for Qdrant volume mount. Add `data_pseudonymization_before_embedding` config flag in R8 extension. Implement DPDP right-to-erasure endpoint.

---

## ADDENDUM: Lavern + Mike + PageIndex Integration

> Added: 2026-05-24. Three new phases (R9, R10, R11) appended after the original R8 phases.
> Sources: AnttiHero/lavern (patterns ported), willchen96/mike (patterns ported), VectifyAI/PageIndex (library).
> Phases R9–R11 are independent of each other but depend on R1–R8 being complete first.

---

### A1. Additional Dependencies

Add to `[project] dependencies` in `pyproject.toml`:

| Package | Version Pin | Reason |
|---|---|---|
| `pageindex` | `>=0.2.0` | VectifyAI PageIndex vectorless RAG — tree-index over PDFs, page-precise citations |
| `litellm` | `>=1.40` | Multi-provider LLM routing (OpenAI, Anthropic, Google) for LLM Council and BYOK |
| `redlines` | `>=0.4.0` | Python library for generating redline DOCX with tracked changes |
| `deepdiff` | `>=6.7` | Diff computation between document versions for version history |
| `sentence-transformers` | `>=2.7` | Semantic similarity for citation grounding verifier (already may be present via retriever) |

Add new `[project.optional-dependencies]` groups:

```toml
[project.optional-dependencies]
lavern = [
    "sentence-transformers>=2.7",
]

mike = [
    "redlines>=0.4.0",
    "deepdiff>=6.7",
    "litellm>=1.40",
]

pageindex = [
    "pageindex>=0.2.0",
    "litellm>=1.40",
]
```

Dev dependencies to add:
- `pytest-asyncio>=0.23` — already likely present; verify for new async agent tests
- `respx>=0.21` — already planned for R1; also needed for PageIndex HTTP mock

---

### A2. New Files Map (Phases R9–R11)

| File Path | What and Why |
|---|---|
| `lexagent/agents/specialist_roster.py` | Defines all 67 Indian legal specialist agents as typed dataclasses: `{name, role, system_prompt_path, model, max_turns, specialisation_keywords}`. Categories: Litigation (HC, SC, trial court, family, criminal, arbitration, NCLT/NCLAT, consumer forum, revenue tribunal), Corporate/Transactional (M&A, PE, IP, FEMA/RBI, SEBI, insolvency, company secretary, taxation), Drafting (contract drafter, pleading drafter, conveyancing, will/trust, employment), Research (legal researcher, citation specialist, comparative law), Review/Verification (red team, blue team, managing partner, risk pricer, plain-English summarizer, client counsellor), Firm Operations (intake specialist, conflict checker, deadline tracker, billing reviewer, matter closer). |
| `lexagent/agents/prompts/` | Directory of 67 `.txt` system prompt files, one per specialist. Each file: role declaration, Indian law jurisdiction scope (BCI rules, IPC, CPC, IEA, etc.), task scope, output format, quality criteria. File naming: `{role_slug}.txt` (e.g., `litigation_hc.txt`, `red_team.txt`, `risk_pricer.txt`). |
| `lexagent/nodes/firm_council.py` | 67-agent Indian firm council mode. `run(state) -> dict`. Reads `firm_council_query` from state, selects relevant specialists from roster by `specialisation_keywords` match, launches them via `asyncio.gather()` with isolated state per agent, collects findings into `firm_council_results`. NOT the same as Phase R3 parallel agents — this mode spawns role-specialists, not task-splits. |
| `lexagent/tools/debate_board.py` | Shared debate board tool (ported from Lavern `debate-board.ts`). `SessionDebateBoard` class with methods: `post_finding(agent_id, finding, evidence, citation)`, `challenge(challenger_id, finding_id, objection, counter_evidence)`, `resolve_debate(moderator_id, finding_id, resolution, reasoning)`. Board state stored in Redis or in-memory dict keyed by `matter_id`. Agents call this tool mid-research. Lawyer triggers via `/debate {matter_id}` slash command. |
| `lexagent/tools/grounding_verifier.py` | Citation grounding verifier (strengthened from Lavern `grounding-verifier.ts`). Two-pass: (1) `string_match_grounding(citation, source_text)` — direct substring match, fast, zero cost; (2) `semantic_grounding(citation, source_text, threshold)` — sentence-transformers cosine similarity when string match fails, configurable threshold (default 0.75). Returns `{grounded: bool, method: "string"\|"semantic"\|"failed", score: float, matched_excerpt: str}`. Used by both the citation enforcement gate (R1) and the verification engine (R9). |
| `lexagent/tools/verification_engine.py` | Multi-pass verification pipeline (ported from Lavern `verification-engine.ts`). Two modes: **fast** (3-pass: `accuracy`, `grounding`, `risk`) and **deep** (10-pass: `context`, `accuracy`, `completeness`, `grounding`, `risk`, `legal_design`, `jurisdiction_fit`, `procedural_compliance`, `client_impact`, `managing_partner_review`). Each pass is an async LLM call with a specialist prompt. `run_verification(draft_text, findings, mode) -> VerificationReport`. Report includes per-pass score (0-100) and notes. Toggled via `verification_mode` config or `/verify-deep` slash command. |
| `lexagent/tools/precedent_board.py` | Persistent precedent memory board. `PrecedentBoard(matter_id, firm_id)` with methods: `add_precedent(case_name, citation, relevance_summary, doc_excerpt)`, `get_precedents(query, top_k)`, `mark_used(citation)`. Backed by Qdrant `{firm_id}_judgments` collection. Survives restarts. The research ReAct agent checks this before calling Kanoon — avoids re-fetching judgments already verified. |
| `lexagent/tools/scoring_engine.py` | Agent output quality scorer (ported from Lavern `scoring-engine.ts`). `score_output(agent_id, output_text, task_type) -> {quality_score: float, dimension_scores: dict, feedback: str}`. Dimensions: citation coverage, legal reasoning depth, jurisdiction accuracy, output completeness, writing clarity. Scores stored per-agent per-matter in mem0 agent layer. Used by LLM Council to weight votes. |
| `lexagent/tools/docx_redline.py` | DOCX tracked-changes / redline output (ported from Mike `docxTrackedChanges.ts`). `generate_redline(original_text, revised_text, author, output_path) -> str`. Uses `redlines` library to generate `.docx` with Word-compatible tracked changes. `accept_all_changes(docx_path) -> str` produces clean version. Called after lawyer edits are diffed against LexAgent's draft. |
| `lexagent/tools/document_versions.py` | Per-matter document versioning (ported from Mike `documentVersions.ts`). `DocumentVersionStore(matter_id)` with: `save_version(content, doc_type, summary) -> version_id`, `get_version(version_id) -> dict`, `list_versions(doc_type) -> List[dict]`, `diff_versions(v1_id, v2_id) -> str`. Versions stored in Postgres `document_versions` table with `matter_id`, `doc_type`, `version_number`, `content_hash`, `file_path`, `summary`, `created_at`. `deepdiff` used for text diffing. |
| `lexagent/tools/byok_manager.py` | Per-user/per-firm encrypted API key storage (ported from Mike `userApiKeys.ts`). Two modes: **individual** — per-lawyer, per-provider keys (`{user_id}_{provider}` key in Postgres, encrypted with AES-256-GCM using `LEX_ENCRYPTION_KEY`); **firm** — single shared key per provider per firm, accessible by all firm members. `BYOKManager.get_key(user_id, provider, firm_id) -> str`, `set_key(user_id, provider, key, firm_id)`, `delete_key(user_id, provider, firm_id)`. Providers: `anthropic`, `openai`, `google`. |
| `lexagent/tools/llm_provider.py` | Multi-provider LLM tool schema normaliser (ported from Mike `llm/tools.ts`). `to_claude_tools(tools: list) -> list`, `to_openai_tools(tools: list) -> list`, `to_gemini_tools(tools: list) -> list`. Converts LangChain `StructuredTool` objects to each provider's native tool schema format. `ProviderRouter` class: `get_llm(provider, model, api_key) -> BaseLanguageModel` — returns the correct LangChain LLM wrapper. LLM Council uses this so each council agent can use a different provider without provider-specific glue code in the orchestrator. |
| `lexagent/tools/pageindex_retriever.py` | PageIndex vectorless RAG retriever. `PageIndexRetriever(workspace_dir, api_key)` with: `index_document(pdf_path, doc_id) -> tree_dict` (lazy — called on first query for that doc, tree cached to `~/.lexagent/pageindex/{doc_id}/_meta.json`), `retrieve(query, doc_id, top_k) -> List[dict]` (returns `{section_title, content, start_page, end_page, relevance_score}`), `get_page_citation(doc_id, start_page, end_page) -> str` (formats Indian citation style with page numbers). Wraps `PageIndexClient` from the `pageindex` library. |
| `lexagent/tools/hybrid_retriever_v2.py` | Autonomous retriever router (replaces `hybrid_retriever.py` for matters with large docs). `HybridRetrieverV2.retrieve(query, matter_id, firm_id) -> List[dict]`. Decision logic: if any document in the matter exceeds `pageindex_long_doc_threshold_pages` (default 20) AND `pageindex_enabled=True` → use PageIndex for that document; short docs and judgment summaries → Qdrant. Returns merged, de-duplicated results with `source: "pageindex"\|"qdrant"` tag per result. |
| `lexagent/tools/citation_formatter.py` | Indian legal citation formatter. `format_citation(case_name, reporter, year, page, court) -> str` — produces Indian citation styles: AIR format (`AIR 2024 SC 123`), SCC format (`(2024) 5 SCC 456`), page-precise (`...at page 7`). Also `format_statute_ref(act, section, sub_section) -> str`. Used by research node and cite node to standardise all citation output. |
| `lexagent/skills/bundle_templates/ni_act_138.yaml` | (already in original plan — no change) |
| `tests/test_firm_council.py` | Tests for 67-agent firm council mode (mock asyncio.gather). |
| `tests/test_debate_board.py` | Tests for debate board post/challenge/resolve flow. |
| `tests/test_verification_engine.py` | Tests for 3-pass and 10-pass verification modes. |
| `tests/test_grounding_verifier.py` | Tests for string-match and semantic grounding (mock sentence-transformers). |
| `tests/test_precedent_board.py` | Tests for precedent add/get/mark_used (mock Qdrant). |
| `tests/test_docx_redline.py` | Tests for redline DOCX generation and accept-all-changes. |
| `tests/test_document_versions.py` | Tests for version save/get/list/diff (mock Postgres). |
| `tests/test_byok_manager.py` | Tests for individual and firm BYOK modes, encryption round-trip. |
| `tests/test_llm_provider.py` | Tests for toClaudeTools, toOpenAITools, toGeminiTools schema conversion. |
| `tests/test_pageindex_retriever.py` | Tests for PageIndex lazy indexing, retrieve, citation format. |
| `tests/test_hybrid_retriever_v2.py` | Tests for autonomous routing decision (long doc → PageIndex, short → Qdrant). |
| `tests/test_citation_formatter.py` | Tests for AIR, SCC citation format output. |

### Significantly changed existing files (Phases R9–R11 additions)

| File Path | Additional Changes |
|---|---|
| `lexagent/nodes/research.py` | Citation grounding now uses `grounding_verifier.py` dual-pass (string + semantic) instead of citation gate string-only check. `PrecedentBoard.get_precedents()` called before Kanoon API — cache hit skips API call. |
| `lexagent/nodes/cite.py` | Replace current string-match with `grounding_verifier.py` — uses semantic fallback when exact match fails. All page numbers added to `page_citations` state field via `citation_formatter.py`. |
| `lexagent/nodes/draft.py` | Optional redline output — if `state["redline_mode"]` and previous version exists, call `docx_redline.py` to produce tracked-changes DOCX alongside clean DOCX. Calls `document_versions.py` to save every completed draft as a new version. |
| `lexagent/nodes/research.py` | `PersistentQdrantRetriever` replaced by `HybridRetrieverV2` which autonomously routes to PageIndex for long docs. |
| `lexagent/graph.py` | Add `firm_council` node. Add conditional edge: `if state["firm_council_mode"] → firm_council → verification → END`. Add `verification` node. |
| `lexagent/gateway/control_plane.py` | Add BYOK endpoints: `POST /api/v1/users/{user_id}/keys`, `DELETE /api/v1/users/{user_id}/keys/{provider}`. Add `GET /api/v1/matters/{matter_id}/versions`, `GET /api/v1/matters/{matter_id}/versions/{v_id}`. Add `POST /api/v1/matters/{matter_id}/verify` (triggers verification engine on latest draft). |
| `lexagent/cli.py` | Add: `lex firm-council {brief}`, `lex verify {matter_id} --mode=fast|deep`, `lex redline {matter_id}`, `lex versions {matter_id}`, `lex byok set {provider} {key}`, `lex byok list`. |
| `lexagent/tools/registry.py` | Register `debate_board`, `grounding_verifier`, `verification_engine`, `precedent_board`, `scoring_engine` as ToolRegistry tools so specialist agents can call them. |

---

### A3. Additional LexState Fields (Phases R9–R11)

```python
# --- Lavern: Firm Council Mode (Phase R9) ---
firm_council_mode: Optional[bool]              # True activates 67-agent Indian firm council
firm_council_query: Optional[str]              # Task description routed to firm council
firm_council_results: Optional[List[dict]]     # [{agent_name, role, finding, quality_score, model}]
debate_board_findings: Optional[List[dict]]    # Active postings on the shared debate board
debate_challenges: Optional[List[dict]]        # Challenges raised against findings
debate_resolutions: Optional[List[dict]]       # Resolved debate entries
verification_mode: Optional[str]               # "fast" (3-pass) | "deep" (10-pass)
verification_report: Optional[dict]            # {pass_name: {score, notes}, overall_score}
grounding_report: Optional[List[dict]]         # [{citation, grounded, method, score, excerpt}]
precedent_board_hits: Optional[List[dict]]     # Precedents retrieved from board before Kanoon

# --- Mike: Redlining + Versioning + BYOK (Phase R10) ---
redline_mode: Optional[bool]                   # True → produce redlined DOCX alongside clean DOCX
redline_output_path: Optional[str]             # Path to generated redlined DOCX
document_versions: Optional[List[dict]]        # [{version_id, version_num, doc_type, summary, created_at}]
active_version_id: Optional[str]               # Currently active document version
byok_provider: Optional[str]                   # "anthropic" | "openai" | "google"
llm_provider_mode: Optional[str]               # Mirrors byok_provider; used by LLM Council normaliser

# --- PageIndex: Vectorless RAG (Phase R11) ---
pageindex_trees: Optional[dict]                # {doc_id: tree_dict} — cached PageIndex trees for this matter
retriever_mode: Optional[str]                  # "pageindex" | "qdrant" | "auto" (auto = HybridRetrieverV2)
page_citations: Optional[List[dict]]           # [{citation, page_number, section_title, excerpt}]
retriever_routing_log: Optional[List[dict]]    # [{doc_id, doc_pages, routed_to, reason}] — audit trail for routing decisions
```

---

### A4. Additional LexConfig Fields (Phases R9–R11)

```python
# Phase R9: Lavern — Firm Council + Verification
firm_council_enabled: bool = Field(False, ...)
firm_council_agent_count: int = Field(67, ...)        # Can be reduced for cost control
firm_council_specialist_selector: str = Field("keyword", ...)  # "keyword" | "llm" (LLM selects relevant agents)
verification_mode: str = Field("fast", ...)            # "fast" (3-pass) | "deep" (10-pass)
verification_fast_passes: str = Field("accuracy,grounding,risk", ...)
verification_deep_passes: str = Field("context,accuracy,completeness,grounding,risk,legal_design,jurisdiction_fit,procedural_compliance,client_impact,managing_partner_review", ...)
grounding_semantic_threshold: float = Field(0.75, ...)
grounding_semantic_enabled: bool = Field(True, ...)
debate_board_enabled: bool = Field(True, ...)
precedent_board_enabled: bool = Field(True, ...)

# Phase R10: Mike — Redlining + Versioning + BYOK + Multi-provider
redline_enabled: bool = Field(False, ...)
document_versioning_enabled: bool = Field(True, ...)
byok_mode: str = Field("individual", ...)              # "individual" | "firm"
byok_providers: str = Field("anthropic,openai,google", ...)
multi_provider_enabled: bool = Field(False, ...)       # Enables LLM Council across providers

# Phase R11: PageIndex — Vectorless RAG
pageindex_enabled: bool = Field(False, ...)
pageindex_api_key: Optional[str] = Field(None, ...)
pageindex_workspace_dir: str = Field("~/.lexagent/pageindex", ...)
pageindex_long_doc_threshold_pages: int = Field(20, ...)   # Docs above this → PageIndex
pageindex_lazy_index: bool = Field(True, ...)              # Index on first query, not on upload
retriever_auto_mode: bool = Field(True, ...)               # HybridRetrieverV2 auto-routing
```

---

### A5. Phase R9: Lavern — Indian Firm Council + Verification Engine + Debate Board

**Goal:** Transform LexAgent from a solo-agent system into a full Indian legal firm simulation — 67 specialists collaborate, debate, and verify before any output is delivered.

**Build:**

1. **`agents/specialist_roster.py`** — 67 agents across 7 categories:
   - **Litigation (18):** HC Advocate, SC Advocate, Trial Court Advocate, Family Law Specialist, Criminal Defense, NCLT/NCLAT Specialist, Consumer Forum Specialist, Revenue Tribunal, Debt Recovery Tribunal, Motor Accidents Claims Tribunal, Labour Court, Arbitration Specialist, Mediation Specialist, Environmental Tribunal, CCI (Competition Commission), SEBI Adjudicating Officer, RERA Adjudicator, Anti-dumping Tribunal
   - **Corporate/Transactional (15):** M&A Counsel, PE/VC Counsel, IP Specialist, FEMA/RBI Specialist, SEBI Compliance, Insolvency/IBC Specialist, Company Secretary, Direct Tax Counsel, Indirect Tax/GST Counsel, Transfer Pricing Specialist, Employment Law Counsel, Real Estate/RERA, PPP/Infrastructure, Startup/Angel Deals, Cross-border Transactions
   - **Drafting (12):** Commercial Contract Drafter, Court Pleadings Drafter, Conveyancing Specialist, Will/Trust Drafter, Employment Agreement Drafter, JV/Shareholders Agreement, SPA/SHA Drafter, NDA Drafter, Licensing Agreement, Franchise Agreement, Regulatory Filing Drafter, Arbitration Clause Specialist
   - **Research (8):** Legal Researcher, Citation Specialist, Comparative Law Analyst, Legislative History Analyst, Statutory Interpretation Specialist, Constitutional Law Researcher, International Law Analyst, Law Commission Report Analyst
   - **Review/Verification (7):** Red Team (adversarial challenge), Blue Team (defense of draft), Managing Partner (overall quality), Risk Pricer (quantify legal risk), Plain-English Summariser, Client Counsellor (client-facing advice tone), Ethics/BCI Compliance Reviewer
   - **Firm Operations (5):** Intake Specialist, Conflict Checker, Deadline Tracker, Billing Reviewer, Matter Closer
   - **Specialist Consultants (2):** Forensic Accounting Expert, Digital Evidence Specialist

2. **`agents/prompts/`** — One `.txt` prompt file per agent. Each prompt: jurisdiction scope (Indian law + BCI rules), task boundaries, output format, quality bar.

3. **`nodes/firm_council.py`** — Orchestrator:
   - Selects relevant agents from roster by keyword match against `firm_council_query` (or LLM-selects if `firm_council_specialist_selector = "llm"`)
   - Spawns selected agents via `asyncio.gather()` with isolated state copies
   - Each agent's output scored by `scoring_engine.py`
   - High-disagreement findings routed to `debate_board.py`
   - Final synthesis by Managing Partner agent
   - `firm_council_results` written to state

4. **`tools/debate_board.py`** — `SessionDebateBoard`:
   - `post_finding(agent_id, finding, evidence, citation)` → `finding_id`
   - `challenge(challenger_id, finding_id, objection, counter_evidence)` → `challenge_id`
   - `resolve_debate(moderator_id, finding_id, resolution)` → marks finding as `RESOLVED | WITHDRAWN | UPHELD`
   - Board state: in-memory dict per `matter_id`; snapshots to `~/.lexagent/matters/{matter_id}/debate_log.json`
   - Lawyer access: `/debate {matter_id}` shows current board; `/challenge {finding_id} {objection}` posts challenge; `/resolve {finding_id}` asks LLM to resolve

5. **`tools/grounding_verifier.py`** — Two-pass grounding:
   - Pass 1: `string_match_grounding()` — `citation_text in source_text` (case-insensitive, strip punctuation)
   - Pass 2: `semantic_grounding()` — only when Pass 1 fails; sentence-transformers `cosine_similarity(embed(citation), embed(source_passages))` against top-5 passages; threshold 0.75
   - Returns `{grounded, method, score, matched_excerpt}` — `matched_excerpt` becomes `doc_excerpt` in the finding

6. **`tools/verification_engine.py`** — Configurable pipeline:
   - Fast mode (3-pass): `accuracy` → `grounding` → `risk`
   - Deep mode (10-pass): adds `context`, `completeness`, `legal_design`, `jurisdiction_fit`, `procedural_compliance`, `client_impact`, `managing_partner_review`
   - Each pass: async LLM call with pass-specific prompt template + draft text + findings
   - Returns `VerificationReport(passes: dict, overall_score: float, flags: list)`
   - Slash command `/verify-deep {matter_id}` triggers deep mode on latest draft

7. **`tools/precedent_board.py`** — Pre-search cache:
   - Checks `{firm_id}_judgments` Qdrant collection before every Kanoon API call
   - Cache hit returns verified judgment with `doc_excerpt` already stored — free, instant
   - Cache miss proceeds to Kanoon API → Playwright fallback → stores result in precedent board

8. **`tools/scoring_engine.py`** — Quality scoring:
   - 5 dimensions: citation coverage (weight 0.25), legal reasoning (0.25), jurisdiction accuracy (0.2), completeness (0.2), writing clarity (0.1)
   - Score stored to mem0 `agent` layer: `{agent_id}_{matter_id}_quality_score`
   - Aggregate scores used by LLM Council voting (higher score = more weight)

**Files:** CREATE `agents/specialist_roster.py`, `agents/prompts/` (67 files), `nodes/firm_council.py`, `tools/debate_board.py`, `tools/grounding_verifier.py`, `tools/verification_engine.py`, `tools/precedent_board.py`, `tools/scoring_engine.py`. CHANGE `nodes/cite.py`, `nodes/research.py`, `graph.py`, `cli.py`, `tools/registry.py`.

**Success criteria:**
- `lex firm-council "cheque bounce NI Act S.138 complaint"` selects HC Advocate + Criminal Defense + Citation Specialist + Risk Pricer + Red Team automatically, returns merged findings with debate resolutions
- `/verify-deep {matter_id}` runs all 10 passes and returns `VerificationReport` with overall score
- Grounding verifier: string-match pass catches exact quotes; semantic pass catches paraphrased citations with score ≥ 0.75
- Precedent board hit rate > 50% after 10 matters of same type

---

### A6. Phase R10: Mike — Redlining, Document Versioning, BYOK, Multi-Provider

**Goal:** Production-quality document lifecycle: every draft is versioned, lawyers get redlined comparisons when they edit, BYOK lets any provider power any agent, and multi-provider support makes the LLM Council genuinely multi-model.

**Build:**

1. **`tools/docx_redline.py`** — Tracked-changes DOCX:
   - `generate_redline(original_path_or_text, revised_path_or_text, author, output_path) -> str`
   - Uses `redlines` library to produce `.docx` with Word-compatible tracked changes
   - `accept_all_changes(docx_path) -> str` — produces clean DOCX (existing flow unchanged)
   - `extract_changes(docx_path) -> List[dict]` — returns `[{type: "insert"|"delete", text, position}]` for programmatic diff
   - Called automatically in draft node when `redline_mode=True` and a prior version exists
   - Also callable via `lex redline {matter_id}` to redline latest draft against previous version

2. **`tools/document_versions.py`** — Version store:
   - Postgres table: `document_versions(id UUID, matter_id, firm_id, doc_type, version_number INT, content_hash, file_path, summary TEXT, created_at)`
   - `DocumentVersionStore(matter_id, firm_id)` methods: `save_version()`, `get_version()`, `list_versions()`, `diff_versions()` (uses `deepdiff` for text; produces human-readable summary)
   - Draft node saves every completed draft automatically — version 1, 2, 3...
   - Lawyer edits uploaded via `/remember edit: {diff}` create new version with `source: "lawyer_edit"`
   - `GET /api/v1/matters/{matter_id}/versions` — lists all versions
   - `GET /api/v1/matters/{matter_id}/versions/{v_id}` — returns content + diff from previous

3. **`tools/byok_manager.py`** — Encrypted BYOK:
   - **Individual mode** (`byok_mode = "individual"`): Per-lawyer, per-provider key storage. Table: `user_api_keys(user_id, firm_id, provider, encrypted_key, created_at)`. Each key encrypted with AES-256-GCM using `LEX_ENCRYPTION_KEY` + `user_id` as PBKDF2 salt.
   - **Firm mode** (`byok_mode = "firm"`): Single shared key per provider per firm. Table: `firm_api_keys(firm_id, provider, encrypted_key, created_at)`. Accessible by all users of that firm. Encrypted with `LEX_ENCRYPTION_KEY` + `firm_id` as salt.
   - `BYOKManager.get_key(user_id, provider, firm_id) -> Optional[str]` — tries individual first, falls back to firm key, falls back to `LEX_{PROVIDER}_API_KEY` env var
   - CLI: `lex byok set anthropic sk-ant-...`, `lex byok list`, `lex byok delete anthropic`
   - Control plane: `POST /api/v1/users/{user_id}/keys`, `DELETE /api/v1/users/{user_id}/keys/{provider}`

4. **`tools/llm_provider.py`** — Multi-provider normaliser:
   - `to_claude_tools(tools: list[StructuredTool]) -> list` — converts to Anthropic `tools` format
   - `to_openai_tools(tools: list[StructuredTool]) -> list` — converts to OpenAI `tools` format  
   - `to_gemini_tools(tools: list[StructuredTool]) -> list` — converts to Gemini `FunctionDeclaration` format
   - `ProviderRouter.get_llm(provider, model, api_key) -> BaseLanguageModel` — returns `ChatAnthropic`, `ChatOpenAI`, or `ChatGoogleGenerativeAI` with correct params
   - LLM Council orchestrator (`parallel_orchestrator.py`) uses this: each council agent calls `ProviderRouter.get_llm()` with its own provider/model, tool schema auto-converted
   - Eliminates all provider-specific glue code from orchestrator

**Files:** CREATE `tools/docx_redline.py`, `tools/document_versions.py`, `tools/byok_manager.py`, `tools/llm_provider.py`. CHANGE `nodes/draft.py`, `gateway/control_plane.py`, `cli.py`. CREATE `alembic/versions/{hash}_document_versions.py`, `alembic/versions/{hash}_api_keys.py` (Postgres migrations).

**Success criteria:**
- `lex draft "cheque bounce"` → `v1` saved; lawyer edits and re-uploads → `v2` saved; `lex redline M-001` produces `.docx` with tracked changes between v1 and v2
- `lex byok set anthropic sk-ant-abc` → key encrypted in Postgres; `lex byok list` shows `anthropic: ✓ set, firm-shared: no`
- LLM Council with `claude-sonnet-4-6 + gpt-4o + gemini-1.5-pro`: all three agents receive same tool definitions in their native format; no `AttributeError` on tool binding

---

### A7. Phase R11: PageIndex — Vectorless RAG for Long Documents

**Goal:** Indian legal judgments and statutes are routinely 50–300 pages. Qdrant vector search fails on these — embeddings lose long-range context. PageIndex builds a hierarchical tree index (effectively a table of contents with page ranges) and uses LLM reasoning to navigate it. Both systems run in parallel; `HybridRetrieverV2` routes autonomously.

**Build:**

1. **`tools/pageindex_retriever.py`** — PageIndex wrapper:
   - `PageIndexRetriever(workspace_dir, api_key, model)` — wraps `PageIndexClient` from the `pageindex` library
   - `index_document(pdf_path, doc_id) -> dict` — builds tree, saves to `{workspace_dir}/{doc_id}/_meta.json`. **Lazy**: only called on first query for that `doc_id`. If `_meta.json` exists → load from disk, skip LLM calls.
   - `retrieve(query, doc_id, top_k=5) -> List[dict]` — calls `PageIndexClient.get_document()` with query; returns `[{section_title, content, start_page, end_page, relevance_score}]`
   - `get_page_citation(case_name, reporter, year, start_page) -> str` — produces `AIR 2024 SC 123 at page 7` or `(2024) 5 SCC 456 at page 12`
   - PageIndex runs on **raw PDF** directly (not LlamaParse output) — avoids OCR errors propagating into the tree index. PyPDF2/pdfplumber used as fallback if `pageindex` cannot parse.

2. **`tools/hybrid_retriever_v2.py`** — Autonomous router:
   - `HybridRetrieverV2(matter_id, firm_id, cfg)` — initialises both `PageIndexRetriever` and `PersistentQdrantRetriever`
   - `retrieve(query, top_k=10) -> List[dict]` — routing logic:
     - For each doc in the matter, check page count
     - Doc pages > `pageindex_long_doc_threshold_pages` (default 20) AND `pageindex_enabled=True` → PageIndex
     - Doc pages ≤ threshold OR `pageindex_enabled=False` → Qdrant
     - Merge results, de-duplicate by `(citation, start_page)`, re-rank by `relevance_score`
     - Log routing decision to `state["retriever_routing_log"]`
   - `get_routing_summary() -> str` — human-readable: "2 docs via PageIndex (54 pages, 78 pages), 3 chunks via Qdrant"
   - Replaces `PersistentQdrantRetriever` as the default retriever in `research.py` and `react_research.py`

3. **`tools/citation_formatter.py`** — Indian citation standards:
   - `format_air(year, court, page) -> str` — `AIR {year} {court_code} {page}` (e.g., `AIR 2024 SC 123`)
   - `format_scc(year, volume, page) -> str` — `({year}) {volume} SCC {page}`
   - `format_with_page(base_citation, page_number) -> str` — appends `at page {page_number}`
   - `format_statute(act, section, sub=None) -> str` — `Section {section}({sub}) of the {act}`
   - `COURT_CODES` dict: `"Supreme Court of India" → "SC"`, `"Delhi High Court" → "Del"`, etc.
   - Used by research node and cite node to normalise all citations to Indian format

4. **Update `nodes/react_research.py`** (from R1) — swap `PersistentQdrantRetriever` for `HybridRetrieverV2`. All routing is now autonomous inside the retriever.

5. **Config gate** — `pageindex_enabled` defaults to `False`. Enable with `LEX_PAGEINDEX_ENABLED=true` + `LEX_PAGEINDEX_API_KEY=...`. When disabled, `HybridRetrieverV2` falls back to Qdrant-only.

**Files:** CREATE `tools/pageindex_retriever.py`, `tools/hybrid_retriever_v2.py`, `tools/citation_formatter.py`. CHANGE `nodes/react_research.py`, `nodes/research.py`, `nodes/cite.py`.

**Success criteria:**
- A 100-page Supreme Court judgment indexed via PageIndex → `retrieve("limitation period for dishonoured cheque", doc_id, top_k=5)` returns 5 results with `start_page` and `end_page` populated
- Citation formatted as `AIR 2024 SC 123 at page 7` when `page_number` available; falls back to `AIR 2024 SC 123` when not
- `HybridRetrieverV2` routing log shows correct routing: doc with 45 pages → `pageindex`, doc with 8 pages → `qdrant`
- `LEX_PAGEINDEX_ENABLED=false` → Qdrant-only path, all R2A tests still pass

---

### A8. Risk Register Additions (R9–R11)

### Risk 6: 67-agent firm council latency
**Mitigation:** Default `firm_council_enabled=False`. When enabled, specialist selector uses keyword match (fast, no LLM call) by default. Cap `max_turns` per agent at 3. `asyncio.gather()` bounds total wall time to slowest agent — not sum. Target: full council < 90s for typical matter.

### Risk 7: Redline DOCX format compatibility
**Mitigation:** `redlines` library targets Python-docx XML directly. Test against Word 2016, 2019, 365 online, and LibreOffice. Accept-all-changes path must produce identical output to clean draft path (assert `diff_versions(v1, redline_accepted) == ""` in tests).

### Risk 8: PageIndex API key cost on large judgment corpora
**Mitigation:** `pageindex_lazy_index=True` default — tree built only on first query, cached forever. `pageindex_long_doc_threshold_pages=20` default — short docs skip PageIndex entirely. `pageindex_enabled=False` default — zero cost until lawyer opts in. Add `pageindex_monthly_doc_budget` config key for hard cap.

### Risk 9: Multi-provider tool schema divergence
**Mitigation:** `llm_provider.py` unit tests assert schema round-trip: same `StructuredTool` → Claude format → Gemini format → each parsed and callable. Test against tool schema for every tool in ToolRegistry. Pin `litellm` version — schema format changes between minor versions.

### Risk 10: BYOK individual key vs firm key precedence confusion
**Mitigation:** `BYOKManager.get_key()` logs which source was used: `individual_key | firm_key | env_var`. Expose via `GET /api/v1/users/{user_id}/keys/status` which shows per-provider source without revealing the key value. CLI `lex byok list` shows same.

---

### A9. Updated Phase Sequence (Full)

| Phase | Focus | Depends On |
|---|---|---|
| R1 | Research overhaul (Kanoon API + ReAct + citation gate) | — |
| R2A | Qdrant KB infrastructure | R1 |
| R2B | mem0 three-layer memory | R2A |
| R2C | File upload + LlamaParse ingestion | R2A |
| R3 | Parallel agents + LLM Council | R1 |
| R4 | Filing bundle generator | R2B, R3 |
| R5 | Skill creator + third-party connectors | R3 |
| R6 | Translation | R2B |
| R7 | JARVIS full assistant mode | R2B, R5 |
| R8 | DPDP hardening + Docker production | All above |
| **R9** | **Lavern: 67-agent Indian firm council + verification engine + debate board** | **R1, R2A, R2B, R3** |
| **R10** | **Mike: Redlining, document versioning, BYOK, multi-provider normaliser** | **R2A, R8** |
| **R11** | **PageIndex: Vectorless RAG complement for long documents** | **R1, R2A** |
| **R12** | **OpenJustice-style visual workflow editor (node-based, React Flow)** | **R8 complete, lexanodes frontend** |

---

## EXECUTION PRIORITY NOTE

> Added: 2026-05-24. Current sprint priorities before any R9–R12 work begins.

**Immediate priorities (do these first, in order):**

1. **R1 — Research overhaul** is the critical path. The Kanoon API client, ReAct research agent, and citation enforcement gate are the foundation every downstream phase depends on. Nothing built on top of the current Playwright scraper is production-safe.

2. **R8 — DPDP hardening + Docker production** is the security prerequisite. JWT auth, audit logging, payload encryption, and rate limiting must be in place before any multi-user or firm-level feature (BYOK, connectors, council mode) is shipped.

**Only after R1 + R8 pass all success criteria should R2A onward begin.**

R9–R12 are fully planned and ready to implement — but none should be started until the graph is stable and security is tight.

---

## ADDENDUM 2: OpenJustice-Style Visual Workflow Editor

> Added: 2026-05-24. Source: openjustice.ai product concept (node-based legal reasoning builder, React Flow).
> Phase R12 — depends on R8 complete + lexanodes frontend being active.

---

### What OpenJustice Is

OpenJustice.ai is a visual, node-based legal reasoning platform — effectively n8n for legal work. Built on React Flow, it lets lawyers drag-and-drop agent nodes onto a canvas, wire them together with edges that define data flow, and run the resulting graph as a legal workflow. Each node can be an AI agent, a tool call (search, document fetch, OCR), a human review gate, a conditional branch, or a document output step.

This is the same paradigm as LangGraph's `StateGraph` — but with a visual editor surface exposed to non-technical lawyers rather than a Python API.

LexAgent's backend is already a LangGraph `StateGraph`. The missing piece is a React Flow canvas that lets lawyers compose and reconfigure that graph without writing code.

---

### Phase R12: Visual Workflow Editor (OpenJustice Pattern)

**Goal:** Expose LexAgent's LangGraph graph as a visual, node-based editor in the lexanodes Next.js frontend. Lawyers drag agent nodes onto a canvas, connect them, configure per-node parameters, and run the resulting workflow. The graph they build is compiled to a LangGraph `StateGraph` definition and executed by the existing LexAgent backend.

**This is not a rewrite.** The backend graph execution engine (LangGraph), all nodes, all tools, and the control plane are unchanged. R12 adds a visual composition layer on top.

---

### R12 Architecture

```
lexanodes (Next.js frontend)
  └── WorkflowCanvas (React Flow)
        ├── NodePalette — draggable node types
        ├── CanvasEditor — React Flow canvas
        ├── NodeConfigPanel — per-node parameter editor
        └── RunControls — trigger graph, stream output
              ↓ POST /api/v1/workflows/run
lexagent (FastAPI control plane)
  └── WorkflowCompiler
        ├── parse canvas JSON → LangGraph StateGraph definition
        ├── validate node types, edge connections, required fields
        └── invoke compiled graph → stream results back to canvas
```

---

### R12 Node Type Palette

Each palette node maps to an existing LexAgent node or tool:

| Visual Node | Maps To | Config |
|---|---|---|
| **Intake** | `nodes/intake.py` | Matter type, jurisdiction, parties |
| **Research** | `nodes/react_research.py` | Tool toggles (Kanoon, Tavily, eCourts), max iterations |
| **Draft** | `nodes/draft.py` | Document type, tone, skill override |
| **Cite** | `nodes/cite.py` | Grounding mode (string / semantic), threshold |
| **Verify** | `tools/verification_engine.py` | Fast (3-pass) or Deep (10-pass) |
| **Translate** | `nodes/translator.py` | Source/target language, mode (reading/filing) |
| **Bundle** | `nodes/bundle_generator.py` | Template name, output format |
| **Human Gate** | Lavern approval-gate pattern | Gate label, approval prompt text |
| **Firm Council** | `nodes/firm_council.py` | Agent count cap, specialist selector mode |
| **Debate** | `tools/debate_board.py` | Auto-resolve threshold, moderator agent |
| **Condition** | LangGraph conditional edge | Field name, comparison value, true/false branch |
| **Output** | Draft delivery | Telegram / .docx / control plane response |
| **Custom Tool** | `tools/registry.py` registered tools | Tool name, input field mapping |

---

### R12 New Files

| File Path | What and Why |
|---|---|
| `lexanodes/src/app/workflows/page.tsx` | Workflow canvas page — React Flow canvas, node palette sidebar, node config panel, run controls |
| `lexanodes/src/components/workflow/NodePalette.tsx` | Left sidebar with draggable node type cards |
| `lexanodes/src/components/workflow/CanvasEditor.tsx` | React Flow canvas — handles node drop, edge connect, selection |
| `lexanodes/src/components/workflow/NodeConfigPanel.tsx` | Right sidebar — per-node config form, rendered from node schema |
| `lexanodes/src/components/workflow/nodes/` | One React Flow custom node component per node type (intake, research, draft, cite, human-gate, condition, etc.) |
| `lexanodes/src/components/workflow/RunPanel.tsx` | Bottom panel — trigger run, stream output, per-node status indicators |
| `lexanodes/src/trpc/workflow.ts` | tRPC router: `saveWorkflow`, `loadWorkflow`, `listWorkflows`, `runWorkflow` (streams results) |
| `lexanodes/prisma/schema.prisma` additions | `WorkflowDefinition` model: `id`, `userId`, `name`, `canvas_json` (React Flow graph JSON), `compiled_graph_json`, `created_at`, `updated_at` |
| `lexagent/gateway/workflow_compiler.py` | Parses React Flow canvas JSON (`{nodes, edges}`) into a LangGraph `StateGraph` definition. Validates node types, checks for cycles, enforces required start node. Returns compiled graph or validation errors. |
| `lexagent/gateway/control_plane.py` additions | `POST /api/v1/workflows/run` — accepts `{canvas_json, initial_state}`, calls `workflow_compiler.py`, invokes compiled graph, streams `text/event-stream` results with per-node status events. `POST /api/v1/workflows` — save named workflow definition. `GET /api/v1/workflows` — list user's saved workflows. |

---

### R12 Canvas JSON → LangGraph Compiler

The canvas JSON produced by React Flow is a standard `{nodes: [...], edges: [...]}` object. `workflow_compiler.py` translates this:

```python
# Input (React Flow canvas JSON):
{
  "nodes": [
    {"id": "n1", "type": "intake", "data": {"jurisdiction": "Delhi HC"}},
    {"id": "n2", "type": "research", "data": {"tool_toggles": {"kanoon": true}}},
    {"id": "n3", "type": "draft", "data": {"doc_type": "injunction_application"}},
    {"id": "n4", "type": "human_gate", "data": {"gate_label": "Lawyer approval"}},
    {"id": "n5", "type": "output", "data": {"channel": "telegram"}}
  ],
  "edges": [
    {"source": "n1", "target": "n2"},
    {"source": "n2", "target": "n3"},
    {"source": "n3", "target": "n4"},
    {"source": "n4", "target": "n5"}
  ]
}

# Output (compiled LangGraph definition — invoked immediately or saved):
graph = StateGraph(LexState)
graph.add_node("intake", intake_node.run)
graph.add_node("research", react_research_node.run)
graph.add_node("draft", draft_node.run)
graph.add_node("human_gate", human_gate_node.run)
graph.add_node("output", output_node.run)
graph.set_entry_point("intake")
graph.add_edge("intake", "research")
graph.add_edge("research", "draft")
graph.add_edge("draft", "human_gate")
graph.add_edge("human_gate", "output")
graph.add_edge("output", END)
compiled = graph.compile()
```

Condition nodes compile to `add_conditional_edges`. Human gate nodes pause execution via LangGraph's interrupt mechanism.

---

### R12 Streaming Execution to Canvas

When a workflow runs, the control plane streams Server-Sent Events back to the canvas. Each event carries per-node status:

```
event: node_start
data: {"node_id": "n2", "node_type": "research", "timestamp": "..."}

event: node_complete
data: {"node_id": "n2", "output_preview": "Found 3 relevant judgments...", "duration_ms": 4200}

event: node_error
data: {"node_id": "n3", "error": "Draft node: model rate limit"}

event: workflow_complete
data: {"output_path": "/matters/M-001/draft_v1.docx", "total_duration_ms": 18400}
```

The canvas highlights each node in real-time as it executes — green (running), blue (complete), red (error). This matches the Lavern interactive dashboard pattern.

---

### R12 Saved Workflows = Shareable Skill Templates

Saved workflow definitions (React Flow JSON + compiled graph) stored in the `WorkflowDefinition` Postgres table are the visual equivalent of LexAgent's `.md` skill files. A lawyer can:
- Save a workflow as "My NI Act S.138 pipeline"
- Share it with a colleague (read-only or edit permission) — Mike's `workflow_shares` pattern
- Export it as a `.json` file for import by another firm
- Publish it to a community skill library (future)

This gives non-technical lawyers a codeless way to compose the same multi-node pipelines that Phase R5 (skill creator) generates as `.md` files.

---

### R12 Success Criteria

- Lawyer drags `Intake → Research → Draft → Human Gate → Output` onto canvas, connects nodes, presses Run → draft delivered to Telegram in under 30 seconds
- Node config panel renders correct form fields for each node type (jurisdiction dropdown for Intake, tool toggles for Research, doc type selector for Draft)
- Canvas highlights each node green/red in real-time during execution
- Saved workflow survives page reload; loaded back as identical React Flow canvas
- `workflow_compiler.py` rejects cycles, missing entry node, and unknown node types with clear validation errors
- `WorkflowDefinition` shareable by email with edit/read-only permission (matching Mike's `workflow_shares` pattern)

---

### R12 Dependencies

**Frontend additions to lexanodes:**
- `reactflow` — already implicit in the platform; if not installed: `npm install @xyflow/react`
- No new backend Python dependencies — compiler uses only existing LangGraph

**Prerequisite phases:**
- R8 must be complete (JWT auth required for workflow save/run endpoints)
- lexanodes Workflow model already exists in Prisma schema (`Workflow`, `Node`, `Connection` tables) — R12 repurposes or extends these rather than starting from scratch

---

### R12 Risk Register

**Risk 11: Canvas JSON → LangGraph compilation edge cases**
Mitigation: Compiler validates before invoking. Validation errors returned as structured JSON with per-node error messages rendered directly on the canvas node. Never invoke a graph that fails validation.

**Risk 12: React Flow canvas state diverges from compiled graph**
Mitigation: `compiled_graph_json` field in `WorkflowDefinition` always regenerated server-side from `canvas_json` at run time — client canvas is the source of truth, compiler output is derived. No stale compiled graph can run.

**Risk 13: Human gate pause/resume across HTTP requests**
Mitigation: LangGraph checkpointer (SQLite or Postgres) persists graph state at the human gate. Resume via `POST /api/v1/workflows/{run_id}/approve`. Canvas polls `GET /api/v1/workflows/{run_id}/status` until approved or rejected.

**Risk 14: Long-running workflows and SSE connection drops**
Mitigation: Each node result written to Postgres `execution_logs` table (already exists in lexanodes schema). Canvas reconnects via `GET /api/v1/workflows/{run_id}/replay` to replay all events from last known node — no re-execution.
