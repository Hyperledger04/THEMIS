# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LexAgent is an open-source AI agent for Indian litigation practice — built on LangGraph. It takes a matter brief from a lawyer, asks clarifying questions, researches Indian case law, drafts a court-ready document with verified citations, and saves the matter to memory.

**This is a teaching build. Every non-obvious code pattern gets a comment. Optimise for clarity over cleverness.**

## Tech Stack

Python 3.11+, LangGraph ≥0.2, LangChain Core, Typer CLI, Pydantic Settings, SQLite (built-in), python-docx, uv package manager. Default LLM: `claude-sonnet-4-20250514` via Anthropic.

## Commands

```bash
uv sync                         # Install dependencies
python -m lexagent.cli draft "..."  # Run the agent
lex draft "matter brief"        # After pip install lexagent
lex setup                       # First-run wizard (creates SOUL.md)
pytest tests/ -v                # Run all tests
pytest tests/test_state.py -v   # Run single test file
mypy lexagent/                  # Type check
ruff check lexagent/            # Lint
```

## Architecture

### The Graph Flow

All agent logic lives in a LangGraph `StateGraph`. No raw LLM calls outside the graph.

```
intake → research → draft → cite (optional) → review → END
              ↑         |
              └─ loop if intake_complete=False
```

`graph.py` exports `build_graph()` which compiles and returns the runnable graph. Invoke with `graph.invoke(initial_state)` or `graph.astream(initial_state)` for streaming.

### LexState (`lexagent/state.py`)

The `TypedDict` that flows through every node. Key fields:
- `user_input`, `matter_id`, `matter_type`, `parties`, `jurisdiction`, `purpose` — intake fields
- `intake_complete: bool` — gate that controls the intake loop
- `research_findings`, `statutes_cited`, `limitation_analysis` — research outputs
- `draft_output`, `risk_annotations`, `plain_english_summary` — draft outputs
- `citations_verified: bool`, `unverified_citations` — cite node outputs
- `messages: Annotated[List, add_messages]` — full message history (LangGraph-managed)
- `lawyer_soul`, `active_skill`, `error`, `next_node` — meta fields

### Node Contract

Every node in `lexagent/nodes/` must follow:
```python
async def run(state: LexState) -> dict:
    try:
        return {"only_changed_keys": new_value}  # NOT the full state
    except Exception as e:
        return {"error": str(e)}
```
Nodes never store state internally. They never raise — catch everything and set `state["error"]`.

### Tool Registry (`lexagent/tools/registry.py`)

Tools self-register via decorator. Adding a tool = dropping a file in `lexagent/tools/`.

```python
@ToolRegistry.register(name="tool_name", description="...", schema={...})
def my_tool(...) -> dict:
    ...
```

`ToolRegistry.get_langchain_tools()` returns tools in LangChain format for `bind_tools()`.

### Skills System (`lexagent/skills/`)

Skills are `.md` files with YAML frontmatter (`name`, `trigger_keywords`, `matter_types`). The loader in `lexagent/skills/loader.py` scans the directory, matches by trigger keywords, and returns the relevant skill content for injection into the system prompt. Lawyers can write skills in a text editor — no code required.

### Memory System

- `~/.lexagent/SOUL.md` — lawyer identity, bar details, drafting style preferences
- `~/.lexagent/matters/{matter_id}/MEMORY.md` — per-matter running memory
- `~/.lexagent/sessions.db` — SQLite with FTS5 for session history

### Config (`lexagent/config.py`)

All configurable values in `LexConfig(BaseSettings)`. Never hardcode model names, API keys, or paths outside this class. Every field here maps to a future BYOK frontend UI control.

## Code Rules (Non-Negotiable)

1. Add `# LANGGRAPH:` comment the **first time** any LangGraph pattern appears (e.g., first `add_conditional_edges`, first `bind_tools`, first `checkpointer`)
2. Add `# WHY:` comment on any non-obvious decision or constraint
3. Use `rich` for all CLI output — never `print()`
4. All system prompts in `lexagent/prompts/` — never inline strings
5. All config in `LexConfig` — never hardcode model names or paths
6. Use `pyproject.toml` with uv — no `requirements.txt`
7. Write the test first, then the implementation. Run `pytest` after every file change.

## Do NOT

- Use LangChain agents — use LangGraph `StateGraph` only
- Store state inside node functions
- Build the frontend (CLI and Telegram gateway only in this sprint)
- Skip `# LANGGRAPH:` or `# WHY:` comments when the pattern is first introduced

## Build Sequence

Phases are sequential — complete and test each before starting the next. See `LEXAGENT_CLAUDE_CODE_BRIEF.md` §13 for full phase details.

| Phase | Focus | Key Checkpoint |
|---|---|---|
| 1 | Foundation — state, config, intake, draft, graph, CLI | `lex draft "test"` returns a real draft |
| 2 | Memory — SOUL.md, matter memory, SQLite sessions | Output references lawyer's name/style |
| 3 | Skills — loader, skill files, auto-selection | Injunction draft follows civil litigation structure |
| 4 | Tools — registry, kanoon, limitation, research/cite nodes | Citations verified against Indian Kanoon |
| 5 | RAG-quality retrieval + review node + .docx output | `--output draft.docx` with chunk-grounded citations and BM25+vector hybrid search |
| 6 | RAGFlow core features — PDF parsing, query expansion, RAPTOR, GraphRAG, re-ranker | All features off by default; toggled via `LexConfig` env vars |
| 7 | Telegram gateway | Bot accepts brief, returns draft |
| 8 | UX Overhaul, Hearing + Deadline Intelligence | — |

Always the CRG to check files, features and edges. Don't use grep, cat or read before checking the CRG. 
**Current phase: 8 (COMPLETE) — Last completed: Phase 8 (UX overhaul — structured intake question banks, Telegram inline buttons, session persistence, setup wizard, contextual loading messages, .docx auto-delivery, post-draft action menu — 279 tests passing)**

