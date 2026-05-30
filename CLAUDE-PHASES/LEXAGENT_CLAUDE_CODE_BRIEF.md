# LexAgent — Claude Code Build Brief
**For:** Claude Code (agentic coding session)  
**Author:** Brahm (Viral Banana / LexaPrompts)  
**Date:** May 2026  
**Purpose:** Build LexAgent from scratch, step by step, as a learning-first open-source project

---

## 0. Who Is Building This and Why

Brahm is a lawyer-turned-AI-entrepreneur building LexAgent as an open-source project to establish technical reputation in the Indian legal-AI space. He is learning LangGraph as he goes — so every architectural decision must be explained as it is made. Do not skip explanations. Do not assume prior LangGraph knowledge. When you write a new pattern for the first time, add a short comment block above it explaining what it does and why.

He will use Claude Code + Aider for all code generation. He can read, modify, and debug Python. He cannot architect from scratch. He understands legal domain deeply.

**This is a teaching build. Optimise for clarity over cleverness.**

---

## 1. What Is LexAgent

LexAgent is an open-source, self-improving AI agent for Indian litigation practice — built on LangGraph.

**The one-line pitch:** "What Hermes Agent is for developers, LexAgent is for litigators."

It is not a chatbot. It is a structured, stateful agentic workflow that:
1. Takes a legal matter description from a lawyer
2. Asks targeted clarifying questions (intake)
3. Researches relevant Indian case law and statutes
4. Produces a structured, annotated legal document (plaint, application, notice, opinion)
5. Verifies every citation before output
6. Remembers the matter, the lawyer's preferences, and improves over time
7. Reviews and redlines contracts for Indian law compliance
8. Parses uploaded PDFs and DOCXs and builds a searchable matter archive
9. Sends hearing and deadline reminders via Telegram and WhatsApp
10. Manages multiple clients in isolation — one lawyer, many clients, no data leaks

**Long-term vision (not in this sprint):** A full web frontend with BYOK (Bring Your Own Key) model selection, custom tool connectors, custom skill creation, and visual workflow builder (like n8n). This sprint builds the correct foundation for that frontend to plug into cleanly.

---

## 2. Core Design Principles

These are non-negotiable constraints that every architectural decision must respect:

### 2.1 LangGraph-Native
All agent logic lives inside LangGraph state graphs. No raw LLM calls outside the graph. This ensures the frontend can later inspect, pause, and modify any node.

### 2.2 Configuration-First
Every behaviour that a user might want to customise must be driven by a config file or database record — not hardcoded. Model name, system prompt, tool list, skill list — all externalised. This is what makes the BYOK frontend possible later.

### 2.3 Tool Registry Pattern (Like Hermes)
Tools self-register. Adding a new tool means dropping a file in `lexagent/tools/` and adding one decorator. No manual import lists. The registry scans at startup.

### 2.4 Skill Files Are Markdown
Skills are `.md` files in `lexagent/skills/`. The agent reads them and injects the relevant one into the system prompt. A lawyer can write a new skill in a text editor. No code required.

### 2.5 Memory Is Files + SQLite
- `~/.lexagent/SOUL.md` — lawyer's identity, style, bar details
- `~/.lexagent/clients/{client_id}/MEMORY.md` — per-client running memory
- `~/.lexagent/matters/{matter_id}/MEMORY.md` — per-matter running memory
- `~/.lexagent/sessions.db` — SQLite for session history with FTS5 full-text search and vector search (sqlite-vec extension)

### 2.6 Explain Everything
Every non-obvious code block gets a `# WHY:` comment. LangGraph-specific patterns get a `# LANGGRAPH:` comment explaining the concept.

### 2.7 Prompt Caching From Day One
From Phase 3 onwards, every LLM call uses Anthropic's `cache_control` header. SOUL.md + skill content are cached at the system prompt level. Matter memory is injected into the user turn — NOT the system prompt — so the cached system prompt prefix is never broken. This alone reduces input token cost by ~75% on long sessions.

### 2.8 Client Isolation Is Non-Negotiable
Every client's data (memory, documents, messages) is stored under their own `client_id`. The agent always knows which client it is working for and never mixes context. This is enforced in the session router and in every memory read/write call.

---

## 3. Technology Stack

| Layer | Choice | Why |
|---|---|---|
| Agent framework | **LangGraph** (langgraph>=0.2) | Stateful, production-grade, respected in AI engineering community |
| LLM interface | **LangChain Core** (langchain-core) | Provider-agnostic — Claude, GPT, Gemini all work |
| Default LLM | **claude-sonnet-4-20250514** via Anthropic | Best for legal reasoning |
| CLI | **Typer** | Clean, modern, easy to learn |
| Config | **Pydantic Settings** + YAML | Type-safe config with env var override |
| Storage | **SQLite** (built-in) + markdown files | Zero dependencies, works offline |
| Vector search | **sqlite-vec** (SQLite extension) | Semantic search without a separate vector DB — stays zero-dependency |
| Document output | **python-docx** | Court-ready .docx generation |
| PDF parsing | **PyMuPDF (fitz)** | Best Indian PDF rendering; falls back to Tesseract for scanned docs |
| OCR | **pytesseract + Pillow** | Hindi + English for court documents |
| Scheduling | **APScheduler** | Lightweight job scheduler; no Redis/Celery needed for MVP |
| Telegram | **python-telegram-bot** | Lawyer-friendly mobile interface |
| WhatsApp | **Evolution API** (self-hosted via Docker) | Open-source WhatsApp bridge; REST webhooks |
| HTTP server | **FastAPI** | Async webhook receiver for WhatsApp |
| Diffing | **difflib** | Contract redlining without external dependencies |
| Package manager | **uv** | Fast, modern, what serious projects use |
| Testing | **pytest** | Standard |
| Python version | **3.11+** | LangGraph requirement |

---

## 4. Complete File Structure

Build this exact structure. Do not deviate without explaining why.

```
lexagent/
│
├── README.md                          # The viral README — written last
├── pyproject.toml                     # uv-compatible package config
├── .env.example                       # API keys template
├── .gitignore
│
├── lexagent/                          # Main package
│   ├── __init__.py
│   │
│   ├── config.py                      # LexConfig — Pydantic Settings, all configurable values
│   │
│   ├── state.py                       # LexState — the TypedDict that flows through the graph
│   │
│   ├── graph.py                       # build_graph() — assembles the LangGraph StateGraph
│   │
│   ├── nodes/                         # One file per graph node
│   │   ├── __init__.py
│   │   ├── intake.py                  # Node 1: clarifying questions + client/matter setup
│   │   ├── research.py                # Node 2: Indian Kanoon + statute lookup
│   │   ├── draft.py                   # Node 3: document generation
│   │   ├── cite.py                    # Node 4: citation verification
│   │   ├── review.py                  # Node 5: risk annotation + plain English summary
│   │   └── contract_review.py         # Node 6: contract redlining (Phase 7)
│   │
│   ├── tools/                         # Self-registering tool files
│   │   ├── __init__.py
│   │   ├── registry.py                # ToolRegistry — scan, register, dispatch
│   │   ├── kanoon_tool.py             # Indian Kanoon search (wraps existing MCP or direct API)
│   │   ├── ecourts_tool.py            # eCourts case status lookup
│   │   ├── limitation_tool.py         # Limitation Act 1963 calculator
│   │   ├── docx_tool.py               # Generate court-ready .docx from draft
│   │   ├── cause_list_tool.py         # Daily cause list puller
│   │   ├── pdf_tool.py                # PDF text extraction + OCR fallback (Phase 6)
│   │   ├── rag_tool.py                # Semantic search over matter documents (Phase 6)
│   │   └── contract_tool.py           # Contract clause extraction + redlining (Phase 7)
│   │
│   ├── memory/                        # Persistence layer
│   │   ├── __init__.py
│   │   ├── soul.py                    # SOUL.md reader/writer — lawyer identity
│   │   ├── client_memory.py           # Per-client MEMORY.md — NEW (Phase 6)
│   │   ├── matter_memory.py           # Per-matter MEMORY.md read/write
│   │   ├── session_store.py           # SQLite sessions with FTS5
│   │   └── rag_store.py               # sqlite-vec vector store for document RAG (Phase 6)
│   │
│   ├── skills/                        # Skill markdown files + loader
│   │   ├── loader.py                  # Scan skills dir, inject relevant skill into prompt
│   │   ├── civil_litigation.md        # Plaint, WS, injunction, appeals
│   │   ├── legal_notice.md            # Section 80 CPC, demand notices, reply notices
│   │   ├── legal_contract.md          # Contract review, redlining, clause library
│   │   ├── writ_petition.md           # Art. 226/227 HC writs
│   │   └── arbitration.md             # S.9/34/36 Arbitration Act applications
│   │
│   ├── prompts/                       # System prompt templates
│   │   ├── base_system.md             # Core identity — the "SOUL.md" default
│   │   ├── tool_guidance.md           # How the agent should use tools
│   │   ├── contract_review_system.md  # Contract reviewer identity (Phase 7)
│   │   └── research_system.md         # Legal researcher identity (Phase 5)
│   │
│   ├── scheduler/                     # Background task scheduling (Phase 8)
│   │   ├── __init__.py
│   │   ├── jobs.py                    # APScheduler job definitions
│   │   └── reminders.py               # Hearing and deadline reminder logic
│   │
│   ├── gateway/                       # Messaging platform interfaces
│   │   ├── __init__.py
│   │   ├── telegram.py                # Telegram bot — send matter brief, get draft back
│   │   ├── whatsapp.py                # Evolution API webhook handler (Phase 9)
│   │   ├── session_router.py          # Routes messages to correct agent session (Phase 9)
│   │   ├── media_handler.py           # Downloads + extracts media from messages (Phase 9)
│   │   └── delivery.py                # Sends responses back to platforms (Phase 9)
│   │
│   └── cli.py                         # Typer CLI — `lex` command entry point
│
├── api/                               # FastAPI server (Phase 9)
│   ├── __init__.py
│   ├── main.py                        # FastAPI app factory
│   └── webhooks/
│       └── whatsapp.py                # POST /webhooks/whatsapp
│
├── skills/                            # User-level skills (outside package, user-editable)
│   └── README.md                      # How to write your own skill
│
├── tests/
│   ├── test_state.py
│   ├── test_nodes.py
│   ├── test_tools.py
│   ├── test_memory.py
│   ├── test_rag.py                    # Phase 6
│   ├── test_contract_review.py        # Phase 7
│   └── test_reminders.py              # Phase 8
│
└── docs/
    ├── architecture.md                # Explained for non-engineers
    ├── langgraph_concepts.md          # LangGraph concepts as you encounter them
    ├── adding_tools.md                # How to add a new tool (no code knowledge needed)
    ├── prompt_caching.md              # WHY and HOW of Anthropic prompt caching
    └── whatsapp_setup.md              # Evolution API setup guide
```

---

## 5. The LexState — Build This First

`lexagent/state.py` is the foundation. Everything else depends on it.

```python
# lexagent/state.py
# LANGGRAPH: State is a TypedDict that gets passed between every node in the graph.
# Think of it as the "file on the table" — each node reads it, adds to it, and passes it on.
# Nothing is stored in the nodes themselves. Everything lives in state.

from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages

class LexState(TypedDict):
    # --- Input ---
    user_input: str                          # Raw input from lawyer
    matter_id: Optional[str]                 # Unique ID for this matter
    client_id: Optional[str]                 # Unique ID for the client — NEW

    # --- Intake (Phase 1) ---
    matter_type: Optional[str]               # e.g. "civil suit", "writ petition"
    parties: Optional[dict]                  # {"plaintiff": ..., "defendant": ...}
    jurisdiction: Optional[str]              # Court + state
    purpose: Optional[str]                   # What document is needed
    key_clauses: Optional[List[str]]         # Specific reliefs or clauses required
    tone_preference: Optional[str]           # "senior lawyer" or "plain commercial"
    risks_to_address: Optional[List[str]]    # Known risks or sensitivities
    citations_required: Optional[bool]       # Include case law?
    intake_complete: bool                    # Gate: has Phase 1 finished?
    clarifying_questions: Optional[List[str]] # Questions asked to lawyer

    # --- Research (Phase 2) ---
    research_findings: Optional[List[dict]]  # [{case_name, citation, relevance, url}]
    statutes_cited: Optional[List[str]]      # ["CPC O.XXXIX R.1&2", "Specific Relief Act S.38"]
    limitation_analysis: Optional[str]       # Limitation period check result
    rag_context: Optional[str]               # Retrieved document excerpts — NEW (Phase 6)

    # --- Draft (Phase 3) ---
    document_outline: Optional[str]          # Structural outline before full draft
    draft_output: Optional[str]              # Full draft text
    risk_annotations: Optional[List[dict]]   # [{clause, risk_level, note}]
    plain_english_summary: Optional[str]     # 2-3 line client summary

    # --- Contract Review (Phase 7) ---
    contract_text: Optional[str]             # Extracted text of uploaded contract
    redline_output: Optional[str]            # Redlined contract with tracked changes
    contract_risk_flags: Optional[List[dict]] # [{clause, risk_level, issue, redline}]

    # --- Verification ---
    citations_verified: bool                 # Have all citations been checked?
    unverified_citations: Optional[List[str]] # Citations flagged for human review

    # --- Conversation history ---
    messages: Annotated[List, add_messages]  # Full message history (LangGraph managed)

    # --- Meta ---
    lawyer_soul: Optional[dict]              # Loaded from SOUL.md
    active_skill: Optional[str]              # Which skill.md is active
    workflow_mode: Optional[str]             # "draft" | "contract_review" | "research_only"
    error: Optional[str]                     # Any error state
    next_node: Optional[str]                 # For conditional routing
```

---

## 6. The Graph — Build This Second

`lexagent/graph.py` — the LangGraph StateGraph that wires all nodes together.

```python
# lexagent/graph.py
# LANGGRAPH: A StateGraph is a directed graph where:
# - Nodes are Python functions that receive state and return updated state
# - Edges define the flow between nodes
# - Conditional edges let the agent make routing decisions
# The graph compiles into a runnable object. You invoke it like: graph.invoke(initial_state)

from langgraph.graph import StateGraph, END
from lexagent.state import LexState
from lexagent.nodes import intake, research, draft, cite, review, contract_review

def route_after_intake(state: LexState) -> str:
    # LANGGRAPH: Conditional edge — returns the name of the next node as a string
    # This is how the graph makes decisions based on state
    if not state["intake_complete"]:
        return "intake"   # Loop back — more questions needed
    if state.get("workflow_mode") == "contract_review":
        return "contract_review"  # Skip research for contract review
    return "research"     # Move forward to research

def route_after_draft(state: LexState) -> str:
    if state.get("citations_required"):
        return "cite"
    return "review"

def build_graph() -> StateGraph:
    graph = StateGraph(LexState)

    # Register nodes
    graph.add_node("intake", intake.run)
    graph.add_node("research", research.run)
    graph.add_node("draft", draft.run)
    graph.add_node("cite", cite.run)
    graph.add_node("review", review.run)
    graph.add_node("contract_review", contract_review.run)

    # Entry point
    graph.set_entry_point("intake")

    # Edges
    graph.add_conditional_edges("intake", route_after_intake)
    graph.add_edge("research", "draft")
    graph.add_conditional_edges("draft", route_after_draft)
    graph.add_edge("cite", "review")
    graph.add_edge("review", END)
    graph.add_edge("contract_review", END)

    return graph.compile()
```

---

## 7. Node Contracts

Every node must follow this exact contract:

```python
# lexagent/nodes/[name].py

async def run(state: LexState) -> dict:
    """
    Node contract:
    - Input: full LexState
    - Output: dict of ONLY the keys this node changes
    - Never return the full state — LangGraph merges the dict automatically
    - Never raise unhandled exceptions — catch and set state["error"]
    """
    try:
        # ... node logic ...
        return {"key_i_changed": new_value}
    except Exception as e:
        return {"error": str(e)}
```

### Node 1: `intake.py`
**Purpose:** Implements the Phase 1 clarifying questions framework.  
**Logic:**
- On first call: analyse `user_input`, identify what information is missing, generate targeted questions
- On subsequent calls (loop): check if all required fields are now filled in `state`
- When all fields complete: set `intake_complete = True`
- Detect `workflow_mode`: if user uploads a contract → `"contract_review"`, else `"draft"`
- Load `SOUL.md` into `state["lawyer_soul"]`
- Use skill loader to detect `matter_type` and set `state["active_skill"]`
- Required fields before proceeding: `matter_type`, `parties`, `jurisdiction`, `purpose`

**Questions to ask (from your system prompt framework):**
1. What type of document do you need?
2. Who are the parties and what is their relationship?
3. What is the governing jurisdiction and applicable law?
4. What is the purpose or transaction context?
5. What specific clauses, terms, or reliefs must be included?
6. Do you want case law, statutory references, or both?
7. What is the preferred tone?

### Node 2: `research.py`
**Purpose:** Search Indian Kanoon for relevant case law. Look up applicable statutes.  
**Logic:**
- Extract search queries from `matter_type`, `jurisdiction`, `purpose`
- Call `kanoon_tool` with 2-3 targeted queries
- Call `limitation_tool` to check if limitation period is relevant
- Call `rag_tool` to search previously uploaded documents (added in Phase 6)
- Store findings as structured list in `state["research_findings"]`
- Store statute list in `state["statutes_cited"]`
- Store RAG excerpts in `state["rag_context"]`

### Node 3: `draft.py`
**Purpose:** Generate the full legal document.  
**Logic:**
- Load the active skill from `state["active_skill"]`
- Build system prompt: base identity + SOUL.md + active skill + tool guidance
- Inject `rag_context` into user turn (not system prompt — see Section 19 on prompt caching)
- First pass: generate `document_outline` and confirm structure
- Second pass: generate full `draft_output` with numbered headings
- Generate `risk_annotations` — for each critical clause, add H/M/L risk note
- Generate `plain_english_summary` — 2-3 lines max

### Node 4: `cite.py`
**Purpose:** Verify every citation in the draft before output.  
**Logic:**
- Extract all citations from `draft_output` using regex patterns for Indian citation formats
- For each citation, call `kanoon_tool` to verify it exists
- Citations that cannot be verified: add to `state["unverified_citations"]` with note "No verified authority found. Human review required."
- Set `citations_verified = True` when done

### Node 5: `review.py`
**Purpose:** Final quality check and output formatting.  
**Logic:**
- Check `unverified_citations` — if any exist, prepend warning to output
- Format final output with: Title, Parties, Document Body, Risk Annotations, Citations, Plain English Summary
- Optionally call `docx_tool` to generate `.docx` file
- Save to matter memory via `matter_memory.py`
- Append important findings to client memory via `client_memory.py`

### Node 6: `contract_review.py` (Phase 7)
**Purpose:** Review and redline an uploaded contract for Indian law compliance.  
**Logic:**
- Extract contract text from `state["contract_text"]` (already parsed by pdf_tool or docx input)
- Process clause by clause using the `legal_contract.md` skill
- For each clause: assign `risk_level` (HIGH/MEDIUM/LOW), identify `issue`, generate `redline`
- Flag Indian-law-specific traps: non-competes (void under S.27 ICA), unlimited liability, unilateral termination without notice
- Run `kanoon_search` on HIGH-risk clauses to find supporting judgments
- Produce `redline_output` as annotated text + `contract_risk_flags` list
- Save summary to matter memory

---

## 8. Tool Registry Pattern

```python
# lexagent/tools/registry.py
# WHY: Self-registering tools mean adding a new tool = dropping one file.
# No manual import lists. The registry scans the tools/ directory at startup.

from typing import Callable, Dict, Any
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    name: str
    description: str
    func: Callable
    schema: dict          # JSON Schema for the tool's input parameters

class ToolRegistry:
    _tools: Dict[str, ToolDefinition] = {}

    @classmethod
    def register(cls, name: str, description: str, schema: dict):
        """Decorator — use @ToolRegistry.register(...) on any tool function"""
        def decorator(func: Callable):
            cls._tools[name] = ToolDefinition(
                name=name,
                description=description,
                func=func,
                schema=schema
            )
            return func
        return decorator

    @classmethod
    def get_all(cls) -> Dict[str, ToolDefinition]:
        return cls._tools

    @classmethod
    def get_langchain_tools(cls) -> list:
        # LANGGRAPH: Returns tools in LangChain format for bind_tools()
        # This is how you attach tools to an LLM in LangGraph
        from langchain_core.tools import StructuredTool
        return [
            StructuredTool(
                name=t.name,
                description=t.description,
                func=t.func,
                args_schema=t.schema
            )
            for t in cls._tools.values()
        ]
```

Example tool using the registry:
```python
# lexagent/tools/limitation_tool.py
from lexagent.tools.registry import ToolRegistry
from datetime import date, timedelta

@ToolRegistry.register(
    name="calculate_limitation",
    description="Calculate limitation period under Limitation Act 1963 for Indian courts",
    schema={
        "type": "object",
        "properties": {
            "cause_of_action": {"type": "string"},
            "cause_of_action_date": {"type": "string", "description": "YYYY-MM-DD"},
            "matter_type": {"type": "string"}
        },
        "required": ["cause_of_action", "cause_of_action_date"]
    }
)
def calculate_limitation(cause_of_action: str, cause_of_action_date: str, matter_type: str = "") -> dict:
    # Limitation Act 1963 schedule lookup
    # Returns: period, expiry_date, article_reference, is_expired, days_remaining
    ...
```

---

## 9. SOUL.md Format

This is the lawyer's identity file. It lives at `~/.lexagent/SOUL.md`. Created on first run via a setup wizard.

```markdown
# Lawyer Identity

**Name:** [Full name]
**Bar Enrollment:** [Number and State Bar Council]
**Practice Since:** [Year]

## Practice Profile
**Primary Courts:** [e.g., Delhi High Court, Saket District Court]
**Primary Practice Areas:** [e.g., Civil Litigation, Arbitration, IP]
**Typical Matter Types:** [e.g., injunctions, recovery suits, writs]

## Drafting Style
**Preferred Tone:** [Senior formal / Plain commercial]
**Citation Preference:** [Always include / Only when critical / Ask each time]
**Document Length:** [Comprehensive / Concise]
**Language Notes:** [e.g., avoid legalese in client-facing docs]

## Firm Context
**Firm Name:** [If applicable]
**Firm Type:** [Solo / Small firm / Large firm]

## Known Judicial Preferences
[Any notes about specific courts or judges — e.g., "Justice X at Delhi HC prefers concise prayers"]

## Custom Instructions
[Any other preferences the agent should always follow]
```

---

## 10. Skill File Format

Skills live in `lexagent/skills/`. Any `.md` file in this directory is auto-discovered.

```markdown
---
name: civil_litigation
trigger_keywords: [plaint, written statement, injunction, civil suit, CPC, specific performance, recovery]
matter_types: [civil_suit, injunction_application, execution_petition, appeal]
jurisdiction: [Indian courts - all]
---

# Civil Litigation Skill

## When to Use This Skill
Use when the matter involves any civil court proceeding under the Code of Civil Procedure, 1908.

## Document Types Covered
- Plaints (O.VII CPC)
- Written Statements (O.VIII CPC)
- Interim Injunction Applications (O.XXXIX R.1&2 CPC)
- Execution Petitions
- First Appeals / Second Appeals
- Applications under S.151 CPC

## Mandatory Intake Checklist
Before drafting, confirm:
- [ ] Cause title and court
- [ ] Limitation period checked (Article ___, Schedule I, Limitation Act 1963)
- [ ] Jurisdiction — territorial, pecuniary, subject matter
- [ ] Relief sought — specific, quantified where applicable
- [ ] Valuation for court fees

## Structure Template
1. In the Court of [Court Name]
2. [Case Type] No. ___ of ___
3. BETWEEN: [Parties]
4. PLAINT / APPLICATION
5. Most Respectfully Showeth
6. [Numbered paragraphs — facts]
7. CAUSE OF ACTION
8. JURISDICTION
9. LIMITATION
10. VALUATION AND COURT FEES
11. PRAYER
12. VERIFICATION

## Risk Flags
- **HIGH:** Any ground for limitation bar — check Article in Schedule I
- **HIGH:** Jurisdiction challenge — plead all three heads
- **MEDIUM:** Impleadment of necessary parties — O.I R.10
- **LOW:** Court fees valuation discrepancy

## Key Statutes
- Code of Civil Procedure, 1908
- Limitation Act, 1963
- Specific Relief Act, 1963
- Registration Act, 1908 (property matters)

## Citation Patterns
For injunctions, always cite:
- Dalpat Kumar v. Prahlad Singh (1991) 4 SCC 130 — balance of convenience test
- Gujarat Bottling Co. v. Coca Cola Co. (1995) 5 SCC 545 — irreparable harm

## Output Notes
- Always include verification clause
- Number every paragraph
- Bold the prayer
- Separate sheet for court fee computation if pecuniary matter
```

---

## 11. Config System

```python
# lexagent/config.py
# WHY: Everything configurable lives here. This is the foundation for the future
# BYOK frontend — every field here maps to a UI control later.

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, List

class LexConfig(BaseSettings):
    # LLM
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    default_model: str = Field("claude-sonnet-4-20250514", env="LEX_MODEL")

    # Agent behaviour
    max_iterations: int = Field(20, env="LEX_MAX_ITERATIONS")
    auto_verify_citations: bool = Field(True)
    auto_save_matter: bool = Field(True)
    enable_prompt_caching: bool = Field(True)   # Anthropic cache_control — saves ~75% on input tokens

    # Paths
    home_dir: str = Field("~/.lexagent", env="LEX_HOME")
    skills_dir: str = Field("~/.lexagent/skills")
    matters_dir: str = Field("~/.lexagent/matters")
    clients_dir: str = Field("~/.lexagent/clients")
    sessions_db: str = Field("~/.lexagent/sessions.db")

    # Tools (enable/disable individually)
    enable_kanoon: bool = Field(True)
    enable_ecourts: bool = Field(True)
    enable_cause_list: bool = Field(False)  # Requires court credentials
    enable_rag: bool = Field(True)           # Document semantic search
    enable_pdf_parse: bool = Field(True)     # PDF + OCR extraction

    # Scheduling (Phase 8)
    enable_reminders: bool = Field(False)    # Hearing/deadline reminders
    reminder_check_interval_hours: int = Field(24)

    # Telegram
    telegram_bot_token: Optional[str] = Field(None, env="TELEGRAM_BOT_TOKEN")
    telegram_allowed_users: List[int] = Field(default_factory=list)

    # WhatsApp (Phase 9)
    evolution_api_url: Optional[str] = Field(None, env="EVOLUTION_API_URL")
    evolution_api_key: Optional[str] = Field(None, env="EVOLUTION_API_KEY")
    evolution_instance: Optional[str] = Field(None, env="EVOLUTION_INSTANCE")
    whatsapp_webhook_secret: Optional[str] = Field(None, env="WHATSAPP_WEBHOOK_SECRET")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

---

## 12. CLI Design

```bash
# Installation
pip install lexagent
# or: uv add lexagent

# Setup (creates ~/.lexagent/, SOUL.md via wizard, sessions.db)
lex setup

# Core commands
lex draft "I need an injunction application for an urgent property dispute"
lex draft --matter-id M001            # Continue an existing matter
lex draft --client-id C001            # Associate with a specific client
lex research "SC judgments on specific performance after 2020"
lex review contract.pdf               # Contract review mode — Phase 7

# Matter and client management
lex matter list
lex matter show M001
lex client list
lex client show C001
lex client new                        # Create new client profile

# Skills
lex skill list
lex skill add ./my_skill.md

# Config
lex config show
lex config set default_model claude-opus-4-20250514
lex config set enable_cause_list true

# Scheduling (Phase 8)
lex reminder add --matter-id M001 --date 2026-06-15 --note "HC hearing"
lex reminder list

# Gateway
lex gateway telegram start
lex gateway telegram stop
lex gateway whatsapp start            # Phase 9
lex gateway whatsapp stop
```

---

## 13. Build Sequence — Do This In Order

Claude Code must follow this sequence exactly. Do not jump ahead. Each phase produces working, testable code before the next begins. Phases 1 and 2 are complete as specified below. Phases 3–10 are the updated roadmap incorporating the full LexCore architecture.

---

### Phase 1: Foundation ✅ (Do not touch without explaining why)
**Goal: `lex draft "test matter"` works end-to-end, even with stub nodes**

1. `pyproject.toml` — uv-compatible, all dependencies declared
2. `.env.example` — all required API keys documented
3. `lexagent/state.py` — full LexState as specified above
4. `lexagent/config.py` — full LexConfig as specified above
5. `lexagent/nodes/intake.py` — working intake node with LLM call
6. `lexagent/nodes/draft.py` — working draft node with LLM call
7. `lexagent/graph.py` — minimal graph: intake → draft → END
8. `lexagent/cli.py` — `lex draft` command that invokes the graph
9. `tests/test_state.py` — basic state validation tests

**Checkpoint:** Run `lex draft "I need a plaint for a property dispute in Delhi"` and get a real (if simple) draft back.

---

### Phase 2: Memory & Identity ✅ (Do not touch without explaining why)
**Goal: Agent knows who the lawyer is and remembers matters**

10. `lexagent/memory/soul.py` — SOUL.md reader + first-run setup wizard
11. `lexagent/memory/matter_memory.py` — create/read/append matter memory
12. `lexagent/memory/session_store.py` — SQLite init + save/load session
13. Update `intake.py` to load SOUL.md into state
14. Update `draft.py` to use SOUL.md in system prompt
15. Update `cli.py` to create matter ID and save session

**Checkpoint:** Run `lex setup`, fill in SOUL.md. Run `lex draft` — output should reference the lawyer's name and style.

---

### Phase 3: Skills System + Prompt Caching
**Goal: Agent auto-selects the right skill AND uses Anthropic prompt caching to cut token costs by ~75%**

**WHY prompt caching is added here and not later:** Every phase after this builds longer and longer system prompts (SOUL.md + skills + tool guidance). Without caching, each turn re-pays for all of that. Caching it now means Phases 4–10 are free to add more context without worrying about cost explosion.

**Steps:**

16. `lexagent/skills/loader.py` — scan skills dir, select by trigger_keywords
17. `lexagent/skills/civil_litigation.md` — full skill file as per Section 10
18. `lexagent/skills/legal_notice.md`
19. `lexagent/skills/legal_contract.md`
20. Update `intake.py` to detect matter type and set `active_skill`
21. Update `draft.py` to inject active skill into system prompt

**22. Add prompt caching to `draft.py` and `research.py`:**

```python
# lexagent/nodes/draft.py (excerpt showing cache_control pattern)
# WHY: Anthropic's API caches prompt content when you mark it with cache_control.
# The cache key is the full text of the marked block. As long as the system prompt
# doesn't change mid-session, we get a cache HIT on every turn.
# Cache hits cost 10% of normal input token price. This alone saves ~75% on long drafts.
#
# CRITICAL RULE: SOUL.md + skill content go in the SYSTEM prompt (cached).
# Matter memory and RAG context go in the USER TURN (not the system prompt).
# If you put memory in the system prompt, the cache breaks every turn.

def build_cached_system_prompt(soul: dict, skill_content: str) -> list:
    return [
        {
            "type": "text",
            "text": f"{soul['raw_text']}\n\n---\n\n{skill_content}",
            # LANGGRAPH / ANTHROPIC: cache_control marks this block for server-side caching.
            # Anthropic caches up to 4 breakpoints per request.
            # The cache TTL is 5 minutes — warm for any session that replies within 5 min.
            "cache_control": {"type": "ephemeral"}
        }
    ]

def inject_memory_into_user_turn(user_input: str, matter_memory: str, rag_context: str = "") -> str:
    # WHY: Memory goes in the user turn, NOT the system prompt.
    # This keeps the system prompt identical across turns → cache hit every time.
    # The <memory-context> tag tells the model this is background context, not a new question.
    memory_block = f"<memory-context>\n{matter_memory}"
    if rag_context:
        memory_block += f"\n\n<document-excerpts>\n{rag_context}\n</document-excerpts>"
    memory_block += "\n</memory-context>"
    return f"{memory_block}\n\n{user_input}"
```

**Checkpoint:** `lex draft "injunction application"` should:
- Follow the civil litigation skill structure (prayer, verification, numbered paragraphs)
- Log "Cache hit: True" on the second turn of the same session
- Cost visibly less on the second turn (check Anthropic dashboard usage)

**Tests:** `pytest tests/test_skills.py tests/test_caching.py`

---

### Phase 4: Client Memory
**Goal: Agent tracks multiple clients separately. Client A's facts never appear in Client B's session.**

**WHY this is its own phase:** Client isolation is a safety feature, not a nice-to-have. A lawyer working with 50 clients cannot risk context bleed between matters. This must be built and tested before Phase 5 tools add more context into the mix.

**Steps:**

23. `lexagent/memory/client_memory.py`:

```python
# lexagent/memory/client_memory.py
# WHY: Client memory is separate from matter memory.
# Matter memory = facts about THIS case.
# Client memory = facts about THIS CLIENT across ALL their cases.
# Examples of client memory: preferred language, prior matters, corporate structure,
# who the actual decision-maker is (often not the client on record).

import os
from pathlib import Path
from lexagent.config import LexConfig

def get_client_memory_path(client_id: str) -> Path:
    config = LexConfig()
    return Path(config.clients_dir).expanduser() / client_id / "MEMORY.md"

def load_client_memory(client_id: str) -> str:
    path = get_client_memory_path(client_id)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

def append_to_client_memory(client_id: str, note: str) -> None:
    path = get_client_memory_path(client_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        from datetime import date
        f.write(f"\n- [{date.today()}] {note}")

def create_client_profile(client_id: str, name: str, phone: str = "", notes: str = "") -> None:
    path = get_client_memory_path(client_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# Client Profile: {name}\n**ID:** {client_id}\n**Phone:** {phone}\n\n## Notes\n{notes}\n"
    path.write_text(content, encoding="utf-8")
```

24. Add `client_id` generation and client profile creation to `lex client new` CLI command.
25. Update `intake.py` to accept `--client-id` and load client memory into the user turn injection alongside matter memory.
26. Update `review.py` to call `append_to_client_memory()` with a one-line summary after each completed matter.
27. Update `session_store.py` to record `client_id` alongside `matter_id` in every session row.
28. `tests/test_memory.py` — add client isolation test: create two clients, run drafts for each, assert no context bleed.

**Checkpoint:** `lex draft --client-id C001 "..."` and `lex draft --client-id C002 "..."` run in the same session without mixing client memory. `lex client show C001` displays accumulated notes from past matters.

---

### Phase 5: Tools, Research & Citation Verification
**Goal: Agent can search Indian Kanoon, calculate limitation periods, and verify every citation it uses**

**Steps:**

29. `lexagent/tools/registry.py` — full ToolRegistry as per Section 8
30. `lexagent/tools/limitation_tool.py` — Limitation Act 1963 calculator (Articles 1–137 of Schedule I, with extension under S.5 for sufficient cause)
31. `lexagent/tools/kanoon_tool.py`:

```python
# lexagent/tools/kanoon_tool.py
# WHY: Indian Kanoon is the primary free database of Indian case law.
# We call their API (indiankanoon.org/api/) to search and fetch judgments.
# The tool returns structured results: case name, citation, court, date, excerpt, URL.
# The cite.py node uses this tool to VERIFY that a citation the LLM produced actually exists.

import httpx
from lexagent.tools.registry import ToolRegistry

KANOON_API_BASE = "https://api.indiankanoon.org"

@ToolRegistry.register(
    name="kanoon_search",
    description="Search Indian Kanoon for case law. Returns top cases with citation, court, and relevance excerpt.",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Legal issue or case name to search"},
            "court": {"type": "string", "enum": ["Supreme Court", "High Court", "All"], "default": "All"},
            "max_results": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
)
def kanoon_search(query: str, court: str = "All", max_results: int = 5) -> dict:
    # Calls Indian Kanoon search API
    # Returns list of {case_name, citation, court, date, excerpt, url}
    ...

@ToolRegistry.register(
    name="kanoon_fetch",
    description="Fetch the full text of a specific Indian Kanoon judgment by document ID or URL.",
    schema={
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Indian Kanoon document ID"}
        },
        "required": ["doc_id"]
    }
)
def kanoon_fetch(doc_id: str) -> dict:
    ...
```

32. `lexagent/nodes/research.py` — full research node using `kanoon_search` + `limitation_tool`. Stores structured `research_findings` with citation, relevance note, and URL.
33. `lexagent/nodes/cite.py` — citation verification node. Extracts citations using Indian citation regex (`(\(\d{4}\)\s+\d+\s+SCC\s+\d+|AIR\s+\d{4}\s+SC\s+\d+)`), calls `kanoon_fetch` on each, marks unverified ones with `[UNVERIFIED — Human review required]`.
34. Update `graph.py` — add `research` and `cite` nodes as per Section 6.
35. `tests/test_tools.py`

**Checkpoint:** `lex draft "injunction for property dispute"` includes 3 real SC citations verified against Indian Kanoon. Any citation the LLM invented is flagged `[UNVERIFIED]`.

---

### Phase 6: Document Parsing + RAG
**Goal: Lawyer can upload a PDF or DOCX and ask questions against it. Agent cites from uploaded documents.**

**WHY sqlite-vec and not a separate vector database:** LexAgent runs on a lawyer's laptop. Adding PostgreSQL or Qdrant as a dependency would require Docker and devops knowledge. SQLite already exists in the project. sqlite-vec is a loadable extension that adds vector search to SQLite — zero new services, same file, same backup story.

**Steps:**

36. Add `sqlite-vec` and `PyMuPDF` (fitz) and `pytesseract` to `pyproject.toml`.

37. `lexagent/tools/pdf_tool.py`:

```python
# lexagent/tools/pdf_tool.py
# WHY: Indian court documents come in two forms:
# 1. Text PDFs — searchable, extractable with PyMuPDF
# 2. Scanned PDFs — image-only, need OCR (Tesseract)
# We try PyMuPDF first. If the extracted text is empty or mostly gibberish
# (heuristic: less than 50 chars per page average), we fall back to Tesseract OCR.

import fitz  # PyMuPDF
from lexagent.tools.registry import ToolRegistry

@ToolRegistry.register(
    name="parse_document",
    description="Extract text from a PDF or DOCX file. Handles scanned PDFs with OCR fallback.",
    schema={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the PDF or DOCX file"}
        },
        "required": ["file_path"]
    }
)
def parse_document(file_path: str) -> dict:
    # Returns: {text, page_count, method_used ("pymupdf" | "tesseract"), char_count}
    ...
```

38. `lexagent/memory/rag_store.py`:

```python
# lexagent/memory/rag_store.py
# WHY: RAG (Retrieval-Augmented Generation) lets the agent answer questions
# using the lawyer's own uploaded documents — judgments, agreements, precedents.
# We chunk each document into 512-token pieces with 50-token overlap.
# Each chunk gets an embedding (a vector of numbers representing its meaning).
# When the agent needs context, we find the chunks most similar to the query.
# sqlite-vec stores these vectors inside the existing sessions.db file.

import sqlite_vec
import sqlite3
from pathlib import Path

def init_rag_store(db_path: str) -> None:
    # Load sqlite-vec extension, create document_chunks table with FLOAT[1536] column
    ...

def ingest_document(db_path: str, file_path: str, matter_id: str, lawyer_id: str) -> int:
    # 1. Call parse_document() to extract text
    # 2. Chunk text into 512-token pieces with 50-token overlap
    # 3. Embed each chunk using OpenAI text-embedding-3-small (or local model)
    # 4. Insert into document_chunks table
    # Returns: number of chunks inserted
    ...

def rag_search(db_path: str, query: str, matter_id: str = None, top_k: int = 5) -> list[dict]:
    # 1. Embed the query
    # 2. Run cosine similarity search in sqlite-vec
    # 3. Filter by matter_id if provided (isolation: only search this matter's docs)
    # Returns: [{text, source_file, similarity_score}]
    ...
```

39. `lexagent/tools/rag_tool.py` — wraps `rag_store.rag_search()` as a registered tool.
40. Update `research.py` to call `rag_tool` before Kanoon search, prepend results to `state["rag_context"]`.
41. Update `draft.py` to include `rag_context` in the user-turn injection (NOT system prompt — per caching rules).
42. Add `lex matter upload M001 ./agreement.pdf` CLI command — triggers `ingest_document()`.
43. `tests/test_rag.py` — upload a sample PDF, ingest, search, assert top result is relevant.

**Checkpoint:** Upload a precedent judgment PDF. Run `lex draft "application based on the precedent I uploaded"`. Output should cite text from the uploaded document directly.

---

### Phase 7: Contract Review + .docx Output
**Goal: `lex review contract.pdf` produces a redlined risk report as a Word document**

**Steps:**

44. `lexagent/tools/contract_tool.py`:

```python
# lexagent/tools/contract_tool.py
# WHY: Contract review is a separate workflow from legal drafting.
# Instead of generating a document, the agent READS an existing contract
# and produces: (a) a risk flag list, (b) suggested redlines, (c) a summary.
# We use difflib to show before/after for each redlined clause.
# Indian-law-specific checks are hardcoded as heuristics because they are always relevant:
# - Non-compete clauses: void under Section 27 of Indian Contract Act 1872
# - Jurisdiction clauses: must specify Indian courts and governing law
# - Arbitration clauses: check if Arbitration Act 1996 is referenced

import difflib
from lexagent.tools.registry import ToolRegistry

@ToolRegistry.register(
    name="extract_clauses",
    description="Extract and number individual clauses from a contract text.",
    schema={
        "type": "object",
        "properties": {
            "contract_text": {"type": "string"}
        },
        "required": ["contract_text"]
    }
)
def extract_clauses(contract_text: str) -> list[dict]:
    # Returns: [{clause_number, heading, text}]
    ...

@ToolRegistry.register(
    name="generate_redline",
    description="Generate a tracked-changes-style redline showing original and suggested replacement text.",
    schema={
        "type": "object",
        "properties": {
            "original": {"type": "string"},
            "revised": {"type": "string"}
        },
        "required": ["original", "revised"]
    }
)
def generate_redline(original: str, revised: str) -> str:
    # Uses difflib to produce a readable diff
    diff = difflib.unified_diff(
        original.splitlines(), revised.splitlines(),
        lineterm="", fromfile="Original", tofile="Suggested"
    )
    return "\n".join(diff)
```

45. `lexagent/nodes/contract_review.py` — full contract review node (see Section 7, Node 6 for logic).
46. Add `workflow_mode` detection to `intake.py`: if `user_input` contains a file path ending in `.pdf` or `.docx`, set `workflow_mode = "contract_review"` and parse the file immediately.
47. Update `graph.py` — `route_after_intake` already handles `"contract_review"` (see Section 6).
48. `lexagent/tools/docx_tool.py` — update to also produce contract review reports:
    - For drafts: numbered headings, bold prayer, verification clause
    - For contract review: risk table, redline diff per clause, summary page
49. Update `cli.py` — `lex review contract.pdf` command + `--output report.docx` flag.
50. Add `lexagent/nodes/review.py` — final quality check and output formatting (moved from stub to full implementation).
51. `tests/test_contract_review.py` — test with a sample NDA, assert non-compete is flagged HIGH.

**Checkpoint:** `lex review sample_nda.pdf --output review.docx` produces a Word document with: risk table, clause-by-clause redlines, and a summary citing S.27 ICA for the non-compete.

---

### Phase 8: Hearing & Deadline Reminders
**Goal: Agent tracks hearings and deadlines and sends reminder notifications automatically**

**WHY APScheduler and not Celery:** Celery requires a Redis broker — another service to install and maintain. APScheduler runs inside the same Python process and persists jobs to SQLite. For a solo lawyer's laptop, this is all that's needed. When scaling to 100 firms (see Section 25), swap to Celery + Redis.

**Steps:**

52. Add `APScheduler` to `pyproject.toml`.

53. `lexagent/scheduler/jobs.py`:

```python
# lexagent/scheduler/jobs.py
# WHY: APScheduler runs background jobs inside the Python process.
# We use the SQLAlchemyJobStore so jobs survive restarts — stored in sessions.db.
# The scheduler starts when `lex gateway` starts, or can run standalone via `lex reminders start`.

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

def create_scheduler(db_path: str) -> BackgroundScheduler:
    jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")}
    scheduler = BackgroundScheduler(jobstores=jobstores)
    return scheduler
```

54. `lexagent/scheduler/reminders.py`:

```python
# lexagent/scheduler/reminders.py
# WHY: This module contains the actual reminder logic.
# add_hearing_reminder() stores a job in APScheduler that fires N days before the hearing.
# When it fires, check_and_send_reminders() loads the matter memory and sends a contextual
# message — not just "you have a hearing tomorrow" but also the key arguments and strategy.

def add_hearing_reminder(
    scheduler,
    matter_id: str,
    hearing_date: str,   # "YYYY-MM-DD"
    purpose: str,
    court: str,
    notify_days_before: int = 1,
    channels: list = ["cli"]   # "cli" | "telegram" | "whatsapp"
) -> str:
    # Calculates trigger date = hearing_date - notify_days_before
    # Stores job with matter_id so the reminder can load matter memory at fire time
    # Returns job_id for later cancellation
    ...

def fire_reminder(matter_id: str, channels: list) -> None:
    # Called by APScheduler at trigger time
    # 1. Load matter memory for matter_id
    # 2. Build contextual reminder message (hearing date, court, key arguments from memory)
    # 3. Send via each channel in channels list
    ...
```

55. Add `lex reminder add` and `lex reminder list` CLI commands.
56. Update `review.py` to ask: "Would you like me to set a reminder for any upcoming hearings in this matter?" — parse the answer and call `add_hearing_reminder()`.
57. `tests/test_reminders.py` — add a test reminder, mock the fire time, assert the reminder fires with the correct matter context.

**Checkpoint:** `lex reminder add --matter-id M001 --date 2026-06-15 --note "HC hearing on injunction"` creates a reminder. When the date arrives, it prints the matter context to CLI. If Telegram is configured, it sends the reminder there too.

---

### Phase 9: Telegram Gateway (Mobile Interface)
**Goal: Lawyer can use LexAgent from phone — send brief via Telegram, receive formatted draft back**

**Steps:**

58. `lexagent/gateway/telegram.py` — Telegram bot using `python-telegram-bot`:
    - `/start` — onboarding message
    - `/draft <brief>` — triggers the full graph, streams progress messages
    - `/review` + document attachment — triggers contract review workflow
    - `/matter <id>` — show matter memory summary
    - `/reminder <date> <note>` — add a hearing reminder
    - Long output: split at 4096 chars OR send as `.txt` document reply
59. Update `cli.py` — `lex gateway telegram start`
60. Handle voice notes: `python-telegram-bot` can receive voice messages → convert to text via `faster-whisper` (local STT) → feed as `user_input`

**Checkpoint:** Send "Draft an injunction for urgent property dispute, Delhi HC, parties are ABC vs XYZ" to Telegram bot. Receive formatted draft back within 90 seconds.

---

### Phase 10: WhatsApp Gateway via Evolution API
**Goal: Clients and lawyers can interact via WhatsApp. Each WhatsApp number is isolated to one client.**

**WHY Evolution API:** It is self-hosted, open-source, and supports both the official WhatsApp Business API and the unofficial multi-device protocol. It exposes a simple REST API and webhook, which maps cleanly to FastAPI. No monthly SaaS fees.

**Architecture:**
```
WhatsApp Message (phone)
    ↓ Evolution API (Docker container)
    ↓ POST /webhooks/whatsapp
    FastAPI webhook handler
    ↓ session_router.py (lawyer_id + client_id from phone number)
    ↓ LexAgent graph.invoke()
    ↓ delivery.py → Evolution API REST → WhatsApp reply
```

**Steps:**

61. Add `docker-compose.yml` for Evolution API:
```yaml
# docker-compose.yml
# WHY: Evolution API needs to run alongside LexAgent.
# This file lets you start both with `docker compose up`.
services:
  evolution-api:
    image: atendai/evolution-api:latest
    ports:
      - "8080:8080"
    environment:
      - AUTHENTICATION_API_KEY=${EVOLUTION_API_KEY}
    volumes:
      - ./evolution_data:/evolution/instances
```

62. `api/main.py` — FastAPI app factory.

63. `lexagent/gateway/session_router.py`:

```python
# lexagent/gateway/session_router.py
# WHY: Every WhatsApp number maps to exactly one (lawyer_id, client_id) pair.
# The lawyer's own number is the gateway number — it receives ALL client messages.
# We use the sender's phone number as client_id (or look it up in a contacts table).
# This ensures client A's conversation never contaminates client B's session.

def route_whatsapp_message(sender_phone: str, lawyer_phone: str, message_body: str) -> dict:
    # Returns: {lawyer_id, client_id, session_id, message}
    # session_id = f"wa:{lawyer_phone}:{sender_phone}"
    ...
```

64. `lexagent/gateway/media_handler.py` — download PDF/DOCX/voice attachments from Evolution API's media endpoint, save to `~/.lexagent/matters/{matter_id}/uploads/`, return local file path.

65. `lexagent/gateway/whatsapp.py` — Evolution API webhook handler:
    - Handles text, voice (transcribed via faster-whisper), document (routed to pdf_tool)
    - Detects if sender is the lawyer or a client (lawyers see full output; clients see plain-English summary only)
    - Splits long responses into multiple WhatsApp messages (max 4096 chars each)

66. `api/webhooks/whatsapp.py` — FastAPI router: `POST /webhooks/whatsapp`.

67. `lexagent/gateway/delivery.py` — sends text + optional file back to WhatsApp via Evolution API REST.

68. Update `cli.py` — `lex gateway whatsapp start` starts the FastAPI server + Evolution API Docker container.

69. `tests/test_whatsapp_gateway.py` — mock Evolution API webhook, assert correct routing and isolation.

**WhatsApp session key design:**

```python
# WHY: Session keys are deterministic and encode both lawyer and client.
# This means the same lawyer-client pair always maps to the same session,
# so matter memory is correctly accumulated across multiple conversations.
def build_session_key(platform: str, lawyer_phone: str, sender_phone: str) -> str:
    return f"{platform}:{lawyer_phone}:{sender_phone}"
```

**Checkpoint:** Send "Mujhe ek legal notice chahiye" via WhatsApp to the gateway number. Receive intake questions back. Answer them. Receive a formatted legal notice DOCX as a WhatsApp document attachment.

---

### Phase 11: Polish, Docs, and Launch
**Goal: Publish to PyPI. Write the viral README. Record demo GIF.**

70. `README.md` — see Section 14
71. `docs/architecture.md` — explained for non-engineers
72. `docs/prompt_caching.md` — WHY and HOW of Anthropic prompt caching
73. `docs/adding_tools.md` — how to add a new tool (no code knowledge needed)
74. `docs/adding_skills.md` — how to write a skill file
75. `docs/whatsapp_setup.md` — Evolution API setup guide (step by step with screenshots)
76. Record demo GIF: terminal → `lex draft` → 4 questions → annotated plaint with SC citations → `.docx` export → 90 seconds total
77. `pyproject.toml` — publish to PyPI via `uv publish`

---

## 14. The README Structure (Write Last)

```markdown
# LexAgent ⚖️
### The self-improving AI agent for Indian litigation practice

> "What Hermes Agent is for developers, LexAgent is for litigators."

[DEMO GIF HERE — shows: terminal → lex draft → 4 clarifying questions →
annotated plaint with SC citations → .docx export → 90 seconds total]

## What It Does

LexAgent is an open-source agentic workflow that takes a matter brief from
a litigator and produces a court-ready, annotated legal document — with
verified Indian case law citations, limitation period analysis, and a
plain-English client summary.

Built on LangGraph. Runs on your machine. Your data never leaves.

## Quick Start
\`\`\`bash
pip install lexagent
lex setup          # 2-minute wizard — creates your lawyer profile
lex draft "I need an interim injunction application for urgent property
           dispute, Delhi HC, plaintiff is ABC Ltd vs XYZ Developers"
\`\`\`

## What You Get Back
- Numbered plaint / application following CPC structure
- Verified Supreme Court citations with neutral citations
- Risk annotations (High / Medium / Low) on every critical clause
- Limitation period analysis
- Plain-English 3-line client summary
- Export to court-ready .docx

## Contract Review
\`\`\`bash
lex review contract.pdf --output review.docx
\`\`\`
Get a clause-by-clause risk report with redlines, Indian law flags
(non-competes, unlimited liability, unilateral termination), and
suggested replacement language.

## WhatsApp Interface
Connect your WhatsApp number via Evolution API. Send a matter brief.
Get a draft back. Works for voice notes too.

## Self-Improving
LexAgent remembers every matter. It learns your drafting style from SOUL.md.
The more you use it, the better it knows you.

## Roadmap
- [ ] Web UI with BYOK model selection
- [ ] Visual workflow builder (like n8n, for lawyers)
- [ ] Custom tool connectors
- [ ] Bar association skill packs
- [ ] Multi-lawyer firm mode

## Built With
LangGraph · LangChain · Claude · Indian Kanoon API · eCourts MCP · Evolution API

## License
MIT
```

---

## 15. Frontend Architecture Notes (For Future Build)

Do not build the frontend now. But every decision in the backend must make the frontend easy. Here is what the frontend needs from the backend:

### What the frontend will need
- **BYOK:** `LexConfig` already externalises all API keys — frontend just writes `.env`
- **Model selection:** `config.default_model` is already a config field — dropdown maps to it
- **Custom tools:** `ToolRegistry` self-registers — frontend uploads a tool `.py` file, backend imports it
- **Custom skills:** Skills are `.md` files — frontend has a markdown editor that writes to `~/.lexagent/skills/`
- **Visual workflows:** Each LangGraph node is already isolated — frontend renders them as visual blocks
- **BYOK connectors:** Each tool in `tools/` is already independent — frontend enables/disables via config flags
- **Client dashboard:** `client_memory.py` stores per-client notes — frontend renders a client timeline
- **Matter dashboard:** `matter_memory.py` stores per-matter notes — frontend renders matter progress

### The API layer (add in Phase 11 or Phase 12)
Add a FastAPI server that wraps the graph:
```python
POST /api/draft              # Submit matter brief → returns stream of state updates
POST /api/review             # Submit contract file → returns risk report stream
GET  /api/matters            # List matters
GET  /api/matters/{id}       # Get matter memory
GET  /api/clients            # List clients
GET  /api/clients/{id}       # Get client memory
POST /api/clients/{id}/upload # Upload document to RAG store
GET  /api/skills             # List skills
POST /api/skills             # Upload new skill
GET  /api/config             # Get current config
PUT  /api/config             # Update config
GET  /api/reminders          # List scheduled reminders
POST /api/reminders          # Add a reminder
```

LangGraph natively supports streaming state updates — `graph.astream()` — which maps perfectly to a real-time frontend that shows the agent's progress node by node.

---

## 16. What Claude Code Should NOT Do

- Do not use LangChain agents (use LangGraph StateGraph only)
- Do not store state inside node functions (state lives in LexState only)
- Do not hardcode model names outside `config.py`
- Do not hardcode system prompts inline — all prompts go in `lexagent/prompts/`
- Do not use `print()` for output — use `rich` for CLI output
- Do not build the frontend — just the backend and CLI
- Do not skip `# WHY:` and `# LANGGRAPH:` comments
- Do not use `requirements.txt` — use `pyproject.toml` with uv
- Do not put memory or RAG context in the system prompt — always inject into the user turn (breaks the cache)
- Do not mix client contexts — every memory read/write must be scoped to `client_id`
- Do not touch Phase 1 or Phase 2 code without explaining the reason for the change

---

## 17. First Message to Claude Code

Paste this as your opening message:

```
I am building LexAgent — an open-source AI agent for Indian litigation practice,
built on LangGraph. I have a full build brief at LEXAGENT_CLAUDE_CODE_BRIEF.md
which you should read first.

Please start with Phase 3 of the build sequence (Phase 1 and 2 are already complete):
1. Create lexagent/skills/loader.py
2. Create lexagent/skills/civil_litigation.md (full skill file)
3. Create lexagent/skills/legal_notice.md
4. Create lexagent/skills/legal_contract.md
5. Update intake.py to detect matter type and set active_skill
6. Update draft.py to inject skill + add Anthropic prompt caching

For every LangGraph concept you use for the first time, add a # LANGGRAPH:
comment explaining what it does and why. For every Anthropic caching pattern,
add a # WHY: comment explaining the cache_control placement decision.

After Phase 3 is working and tested, stop and ask me to confirm before proceeding
to Phase 4. Build one phase at a time.
```

---

## 18. Learning Path — LangGraph Concepts You Will Encounter

As Claude Code builds each phase, these are the concepts you will learn in order:

| Phase | Concept | What It Is |
|---|---|---|
| 1 | `TypedDict` | Python typed dictionary — how LangGraph state is defined |
| 1 | `StateGraph` | The graph object that holds all nodes and edges |
| 1 | `add_node()` | Registering a function as a graph node |
| 1 | `add_edge()` | Connecting two nodes |
| 1 | `set_entry_point()` | Where the graph starts |
| 1 | `compile()` | Turns the graph definition into a runnable object |
| 1 | `invoke()` | Runs the graph synchronously with an initial state |
| 2 | `astream()` | Runs the graph async, streaming state updates |
| 2 | `add_messages` | Special annotation for message history — LangGraph manages append logic |
| 3 | `conditional_edges` | Route to different nodes based on state values |
| 3 | `cache_control` | Anthropic-specific — marks prompt blocks for server-side caching |
| 4 | Client isolation | Pattern: scope every memory call to `client_id` |
| 5 | `bind_tools()` | Attach tools to an LLM so it can call them |
| 5 | `ToolNode` | Built-in LangGraph node that executes tool calls |
| 6 | `sqlite-vec` | SQLite extension for vector similarity search |
| 6 | RAG pattern | Retrieve → augment user turn → generate |
| 7 | `interrupt()` | Pause graph execution and wait for human input |
| 8 | `checkpointer` | Persist graph state to SQLite between invocations |
| 9 | Telegram webhook | Long-polling vs webhook mode for bot updates |
| 10 | FastAPI webhook | Async HTTP server for Evolution API callbacks |

---

## 19. Prompt Caching Architecture (Anthropic-Specific)

This section explains the caching design so it is clear to every future contributor.

### The Problem
A lawyer's context grows rapidly:
- SOUL.md: ~500 tokens
- Active skill: ~800 tokens
- Tool schemas: ~600 tokens
- Base system prompt: ~300 tokens
- **Total static context: ~2,200 tokens per turn**

On a 20-turn drafting session, that is 44,000 tokens of repeated static content. At claude-sonnet-4 pricing, this adds up quickly.

### The Solution: cache_control Placement

```
SYSTEM PROMPT (cached — never changes mid-session):
┌──────────────────────────────────────────────┐
│  base_system.md                              │
│  + SOUL.md content                           │
│  + active_skill content                      │
│  [cache_control: ephemeral] ← breakpoint here│
└──────────────────────────────────────────────┘

USER TURN (NOT cached — different every turn):
┌──────────────────────────────────────────────┐
│  <memory-context>                            │
│    matter memory (grows each turn)           │
│    client memory                             │
│    RAG excerpts (different each query)       │
│  </memory-context>                           │
│                                              │
│  Actual user question                        │
└──────────────────────────────────────────────┘
```

**Rule:** If it changes between turns → user turn. If it stays the same → system prompt with cache_control.

### Cache TTL
Anthropic's cache TTL is **5 minutes**. Any turn that arrives within 5 minutes of the previous turn gets a cache hit on the system prompt. For a lawyer actively drafting, this is almost always the case.

### Cache Savings Estimate
- Cache hit = 10% of normal input token price
- 20-turn session, 2,200 tokens static per turn = 44,000 tokens total static
- Without caching: 44,000 × full price
- With caching: 2,200 (first turn, full price) + 19 × 2,200 × 10% = 2,200 + 4,180 = 6,380 tokens billed at full price equivalent
- **Saving: ~85% on the static portion of input tokens**

---

## 20. Contract Review Architecture

The contract review workflow is a separate branch of the graph (not a modification to the drafting branch). This is intentional: the two workflows have different intakes, different tools, and different output formats.

### Workflow Trigger
In `intake.py`: if `user_input` contains a file path (`.pdf` or `.docx`), OR the Telegram/WhatsApp message has a document attachment, set `workflow_mode = "contract_review"`. In the graph's conditional edge, this routes to `contract_review` node instead of `research`.

### Indian Law Heuristics (Always Check)
These are hardcoded checks because they apply to virtually every Indian contract:

| Clause Type | Indian Law Issue | Action |
|---|---|---|
| Non-compete | Void under Section 27, Indian Contract Act 1872 | Flag HIGH, suggest deletion or time/geo limitation with severability |
| Unlimited liability | No statutory cap — negotiable, but standard practice is 1x contract value | Flag HIGH, suggest liability cap |
| Unilateral termination without notice | Potentially unfair — Indian courts have granted injunctions | Flag MEDIUM, suggest 30-day notice |
| Jurisdiction: foreign courts only | Foreign judgments need enforcement proceedings in India | Flag HIGH, add Indian courts as alternative |
| Arbitration without Arbitration Act reference | May complicate enforcement | Flag MEDIUM, add "under Arbitration and Conciliation Act 1996" |
| IP assignment: all future IP | Overbroad under Indian Patent Act | Flag MEDIUM, limit to project-specific IP |

### Output Format
Contract review produces two outputs:
1. **`contract_risk_flags`** (list of dicts) — structured data for the CLI table view
2. **`redline_output`** (string) — human-readable diff for the .docx attachment

---

## 21. RAG Architecture (Document Semantic Search)

### Why Chunking Matters
Indian court judgments and contracts are long. A 50-page judgment cannot be sent to the LLM in full — it would exceed the context window and cost a fortune. Chunking splits it into searchable pieces.

### Chunking Strategy
- **Chunk size:** 512 tokens (roughly 400 words)
- **Overlap:** 50 tokens (ensures clause boundaries are captured even if they straddle a chunk boundary)
- **Metadata per chunk:** `{source_file, page_number, chunk_index, matter_id, lawyer_id}`
- **Isolation:** Every RAG search is filtered by `lawyer_id`. Matter-specific searches also filter by `matter_id`.

### Embedding Model Choice
- **Default:** `text-embedding-3-small` (OpenAI, 1536 dimensions) — cheap, fast, good for English + Hindi mixed text
- **Alternative:** `multilingual-e5-large` (local, via sentence-transformers) — for lawyers who want zero API dependency
- **Config field:** `LexConfig.embedding_model` — switch between the two without code changes

### Search Strategy
At query time:
1. Embed the user's query
2. Run cosine similarity search in sqlite-vec, filtered by `matter_id`
3. Return top 5 chunks
4. Inject as `<document-excerpts>` block in the user turn (per caching rules)

### Ingestion CLI
```bash
lex matter upload M001 ./judgment_abc.pdf       # Ingest PDF into matter M001's RAG store
lex matter upload M001 ./agreement_draft.docx   # Ingest DOCX
lex matter docs M001                             # List all ingested documents for this matter
```

---

## 22. Client Memory Architecture

Client memory answers the question: "What do I know about this person across all their matters?"

### File Location
`~/.lexagent/clients/{client_id}/MEMORY.md`

### Content That Goes in Client Memory
- Communication preferences (language, channel, formality)
- Prior matters and outcomes (brief summaries only)
- Corporate structure (for business clients)
- The actual decision-maker (often not the client on record)
- Payment patterns (if relevant)
- Sensitivity flags ("client is anxious — always give timeline estimates")

### Content That Does NOT Go in Client Memory
- Case-specific facts → those go in matter memory
- Document content → that goes in the RAG store
- Hearing dates → those go in the reminders scheduler

### Update Trigger
`review.py` appends to client memory after every completed matter:
```
- [2026-05-17] Completed: Bail application for FIR 234/2024. Outcome: Bail granted on first hearing.
```

### Injection in User Turn
```python
user_message = inject_memory_into_user_turn(
    user_input=user_input,
    matter_memory=load_matter_memory(matter_id),
    client_memory=load_client_memory(client_id),  # Added alongside matter memory
    rag_context=rag_search(query, matter_id)
)
```

---

## 23. Hearing & Deadline Reminder Architecture

### Two Types of Reminders

| Type | Created by | Trigger |
|---|---|---|
| Hearing reminder | `lex reminder add` or `review.py` at matter close | N days before `hearing_date` |
| Limitation reminder | `limitation_tool.py` return value | N days before `expiry_date` |

### Reminder Message Content
A reminder is not just "you have a hearing tomorrow." It includes:
1. Date, time, court, room
2. Matter title and parties
3. Key arguments from matter memory (last 500 chars of MEMORY.md)
4. Any unverified citations flagged for review

### Delivery Channels
- **CLI:** `rich` panel printed to terminal (for `lex reminder check`)
- **Telegram:** Direct message to lawyer's bot
- **WhatsApp:** Evolution API REST call to lawyer's registered number

### Persistence
APScheduler stores jobs in `sessions.db` (SQLAlchemyJobStore). Jobs survive process restarts. Each job carries `matter_id` and `channels` as kwargs — the actual matter memory is loaded at fire time, not at scheduling time, so it reflects the latest state.

---

## 24. WhatsApp Gateway Architecture

### Session Key Design
```python
# Format: {platform}:{lawyer_gateway_phone}:{sender_phone}
# This ensures:
# - Same lawyer-client pair always maps to same session
# - Different clients of same lawyer never share a session
# - Same client on different platforms (WhatsApp vs Telegram) have separate sessions
session_key = f"wa:{lawyer_phone}:{sender_phone}"
```

### Message Types Handled
| Type | Detection | Handling |
|---|---|---|
| Text | default | Route to graph as `user_input` |
| Voice note | `messageType == "audioMessage"` | Download → faster-whisper transcribe → route as text |
| PDF | `messageType == "documentMessage"` with `.pdf` mime | Download → pdf_tool → ingest to RAG or trigger contract review |
| DOCX | `messageType == "documentMessage"` with `.docx` mime | Download → python-docx extract → same as PDF |
| Image | `messageType == "imageMessage"` | Download → pytesseract OCR → treat as text |

### Lawyer vs Client Detection
The gateway number is the lawyer's WhatsApp number. The lawyer can message themselves (from their own phone to the gateway) with full output. All other senders are treated as clients and receive only the `plain_english_summary` output.

### Evolution API Setup (Minimal)
```bash
# 1. Start Evolution API
docker compose up -d

# 2. Create an instance (one per lawyer phone number)
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: YOUR_API_KEY" \
  -d '{"instanceName": "lexagent", "qrcode": true}'

# 3. Scan QR code with WhatsApp on lawyer's phone

# 4. Set webhook to LexAgent's FastAPI server
curl -X POST http://localhost:8080/webhook/set/lexagent \
  -H "apikey: YOUR_API_KEY" \
  -d '{"url": "http://YOUR_SERVER_IP:8000/webhooks/whatsapp", "events": ["MESSAGES_UPSERT"]}'
```

---

## 25. Production Scaling Roadmap (Future Reference)

This section is for reference only. Do not implement in this sprint.

| Scale | What Changes |
|---|---|
| **1 lawyer** | SQLite + APScheduler + Docker Compose. Everything in this brief. |
| **10 lawyers** | Add user accounts table to SQLite. Each lawyer's data in separate subdirectory. APScheduler still fine. |
| **100 law firms** | Migrate to PostgreSQL + pgvector (replace sqlite-vec). Celery + Redis (replace APScheduler). FastAPI scales horizontally. PostgreSQL RLS enforces firm isolation. |
| **LLM cost at scale** | Batch API for non-urgent drafts. `claude-haiku` for intake classification, `claude-sonnet` for drafting. Prompt caching already in place from Phase 3. |
| **WhatsApp at scale** | Evolution API cluster (one instance per 100 phone numbers). Official WhatsApp Business API for high-volume firms. |

---

*Brief version: 2.0 — May 2026*  
*Author: Brahm / Viral Banana*  
*License: MIT (same as LexAgent)*
*Updated to incorporate LexCore architecture research (Hermes Agent analysis + LexCore redesign)*
