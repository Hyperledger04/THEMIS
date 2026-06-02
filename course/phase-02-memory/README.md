# Phase 2 — Memory: SOUL.md, Matter Memory, SQLite

> **Status: Coming soon.** Complete Phase 0 and Phase 1 first.

## What you will build

By the end of this phase, your agent will:
- Load the lawyer's identity and drafting preferences from `~/.lexagent/SOUL.md`
- Save a running summary of every matter to `~/.lexagent/matters/{matter_id}/MEMORY.md`
- Store and query sessions in SQLite with FTS5 full-text search

## The files you will understand

- `lexagent/memory/soul.py` — `load_lawyer_soul()`, `run_setup_wizard()`
- `lexagent/memory/matter_memory.py` — `save_matter_memory()`, `load_matter_memory()`
- `lexagent/memory/session_store.py` — SQLite with FTS5, `SessionStore` class
- `lexagent/memory/wisdom.py` — accumulates cross-matter insights

## Key concepts

- **SOUL.md as identity** — a Markdown file as a persistent "persona" for the LLM
- **File-based memory vs database memory** — when to use each
- **SQLite FTS5** — full-text search built into Python's standard library
- **Why matter memory is separate from LangGraph checkpoints** — different granularity

## Coming in this phase

1. `01_soul_md.py` — what SOUL.md is, how it's loaded, how it shapes the system prompt
2. `02_matter_memory.py` — per-matter memory, append vs overwrite patterns
3. `03_sqlite_fts5.py` — SQLite from first principles, FTS5 for legal text search
4. `04_session_store.py` — the full SessionStore implementation
5. `exercises/ex01_build_soul_loader.py` — write your own SOUL.md loader
6. `exercises/ex02_build_matter_memory.py` — implement save/load matter memory
