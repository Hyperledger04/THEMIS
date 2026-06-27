# LexAgent (Themis) — Learn-by-Building Course

You are going to build LexAgent from scratch. By the end you will understand every line in this repo, be able to fix anything that breaks, and extend it with new features on your own.

The course is organized as the project was actually built — phase by phase. Each phase adds one big idea on top of the last. No phase assumes knowledge beyond what the previous one taught.

> **Note on naming:** The package was renamed from `lexagent` to `themis` (commit `552f1d5`).
> All source code now lives in `themis/`. The CLI command is still `lex`. The data directory is `~/.themis/`.

---

## How to use this course

Each phase lives in its own folder. Inside you will find:
- A `README.md` explaining the concepts in plain language
- Python files (`.py`) with working code, extensive comments, and "Pause and think" boxes
- An `exercises/` folder with problems that make you write the real thing yourself
- A `_lexagent_connection.md` showing exactly where each concept appears in the actual codebase

**Rule:** read the README first, run every `.py` file, then do every exercise before moving to the next phase. The exercises are not optional — they build the intuition that lets you fix bugs in the future.

```bash
cd "/Users/anshoosareen/Lexagent/course/phase-00-python-foundations"
python 01_python_basics.py   # run it, read the output, ask questions
```

---

## Full Curriculum

| Phase | Folder | Status | What you build | Big ideas |
|-------|--------|--------|---------------|-----------|
| 0 | `phase-00-python-foundations` | ✅ | Python intuition toolkit | Types, async/await, TypedDict, Pydantic Settings, .env files |
| 1 | `phase-01-langgraph-core` | ✅ | A working 3-node agent | StateGraph, nodes, edges, conditional routing, human-in-the-loop |
| 2 | `phase-02-memory` | ✅ | Persistent matter memory | SOUL.md, SQLite, matter memory, session store |
| 3 | `phase-03-skills` | ✅ | Domain-specific prompts | Markdown-as-config, YAML frontmatter, skill loader |
| 4 | `phase-04-tools-and-apis` | ✅ | Real case law retrieval | Tool registry, HTTP clients, Indian Kanoon API |
| 5 | `phase-05-rag-and-retrieval` | ✅ | Grounded citations | Chunking, BM25, TF-IDF, hybrid retrieval |
| 6 | `phase-06-advanced-rag` | ✅ | Production retrieval | RAPTOR, GraphRAG, re-ranker, query expansion |
| 7 | `phase-07-gateways` | ✅ | CLI + Telegram | Typer CLI, async Telegram bot, message routing |
| 8 | `phase-08-ux-and-output` | ✅ | Streaming UX + .docx | Rich, live spinners, python-docx, streaming tokens |
| 9 | `phase-09-systems-design` | ✅ | Production system | FastAPI, Postgres, Qdrant, multi-tenancy, Voice AI |
| 10 | `phase-10-v3-architecture` | ✅ | V3 — Persistent Legal OS | Matter workspace, event runtime, living agent, chamber, planner, doc-haus bridges |
| 11 | `phase-11-privacy-and-safety` | ✅ | Production hardening | Privacy tiers, PII anonymisation, runtime brakes, playbook DAGs |

---

## Phase 0 — Court-Ready Drafting (completed before V3 work)

Before the V3 architecture work began, Phase 0 fixed the three filing-blocking bugs in the draft pipeline:

1. **Lawyer notes contaminating filings** — `docx_writer.py` now splits at `---` and routes Plain English Summary + Risk Assessment to a separate `lawyer_notes.docx`. Only the legal document body goes to the filing docx.
2. **No court header** — replaced "Legal Document" title with a court-profile-aware formal header block driven by SOUL.md preferences.
3. **No filing packet** — `lex draft` now produces `complaint.docx`, `affidavit_evidence.docx`, `witness_list.docx`, `list_of_documents.docx`, `lawyer_notes.docx`.

See `analysis/` in the repo root for the specification documents that drove this work.

---

## Phase 10 — doc-haus Bridge Features (shipped alongside V3 architecture)

Three features from the open-source [doc-haus](https://github.com/sure-scale/doc-haus) TypeScript legal AI were identified as directly portable to the Python/LangGraph stack. They ship *before* the full V3 infrastructure because they are independent of the planner DAGs and subagent contracts.

| Feature | Lesson | Real file |
|---------|--------|-----------|
| Word-native tracked-changes redlining | `phase-10/06_redline_docx.py` | `themis/tools/redline.py` |
| Adversarial multi-agent review (Reviewer → Challenger → Summarizer) | `phase-10/07_adversarial_chamber.py` | `themis/nodes/chamber.py` |
| Grid analysis — same question across all docs in a matter | `phase-10/08_grid_analysis.py` | `themis/nodes/grid.py` |

Activate them:
```bash
lex draft "Review this NDA" --chamber --redline /tmp/original.docx
lex grid my-matter --questions "What is the notice period?" --questions "Who bears indemnity?"
```

---

## Where does each phase live in the codebase?

```
Phase 0 → the language itself
Phase 1 → themis/graph.py, themis/state.py, themis/nodes/
Phase 2 → themis/memory/
Phase 3 → themis/skills/
Phase 4 → themis/tools/, themis/nodes/research.py
Phase 5 → themis/tools/retriever.py, themis/tools/chunker.py, themis/nodes/cite.py
Phase 6 → themis/tools/raptor_summarizer.py, themis/tools/legal_kg.py, themis/tools/reranker.py
Phase 7 → themis/cli.py, themis/gateway/telegram.py
Phase 8 → themis/ui/, themis/tools/docx_writer.py
Phase 9 → themis/gateway/control_plane.py, themis/runtime/, themis/gateway/voice.py
Phase 10 → themis/workspace/, themis/runtime/worker.py, themis/nodes/chamber.py,
            themis/nodes/grid.py, themis/tools/redline.py
Phase 11 → themis/security/tiers.py, themis/security/anonymizer.py
```

---

## Prerequisites

You need Python installed and a terminal. That is all.

```bash
python --version   # anything 3.11+ is fine
```

Install the course dependencies (a small subset of what Themis uses):

```bash
cd "/Users/anshoosareen/Lexagent/course"
pip install pydantic pydantic-settings python-dotenv rich langgraph langchain-core litellm
```

---

## Run the course frontend

A minimal browser-based navigator is included. It renders each phase's README and lets you open lesson files directly.

```bash
cd "/Users/anshoosareen/Lexagent/course"
python serve.py          # opens http://localhost:8765
```

Start with Phase 0.
