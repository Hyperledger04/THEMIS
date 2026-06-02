# LexAgent — Learn-by-Building Course

You are going to build LexAgent from scratch. By the end you will understand every line in this repo, be able to fix anything that breaks, and extend it with new features on your own.

The course is organized as the project was actually built — phase by phase. Each phase adds one big idea on top of the last. No phase assumes knowledge beyond what the previous one taught.

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

| Phase | Folder | What you build | Big ideas |
|-------|--------|---------------|-----------|
| 0 | `phase-00-python-foundations` | Python intuition toolkit | Types, async/await, TypedDict, Pydantic Settings, .env files |
| 1 | `phase-01-langgraph-core` | A working 3-node agent | StateGraph, nodes, edges, conditional routing, human-in-the-loop |
| 2 | `phase-02-memory` | Persistent matter memory | SOUL.md, SQLite, matter memory, session store |
| 3 | `phase-03-skills` | Domain-specific prompts | Markdown-as-config, YAML frontmatter, skill loader |
| 4 | `phase-04-tools-and-apis` | Real case law retrieval | Tool registry, HTTP clients, Indian Kanoon API |
| 5 | `phase-05-rag-and-retrieval` | Grounded citations | Chunking, BM25, TF-IDF, hybrid retrieval |
| 6 | `phase-06-advanced-rag` | Production retrieval | RAPTOR, GraphRAG, re-ranker, query expansion |
| 7 | `phase-07-gateways` | CLI + Telegram | Typer CLI, async Telegram bot, message routing |
| 8 | `phase-08-ux-and-output` | Streaming UX + .docx | Rich, live spinners, python-docx, streaming tokens |
| 9 | `phase-09-systems-design` | Production system | FastAPI, Postgres, Qdrant, multi-tenancy, Voice AI |

---

## Where does each phase live in LexAgent?

```
Phase 0 → the language itself
Phase 1 → lexagent/graph.py, lexagent/state.py, lexagent/nodes/
Phase 2 → lexagent/memory/
Phase 3 → lexagent/skills/
Phase 4 → lexagent/tools/, lexagent/nodes/research.py
Phase 5 → lexagent/tools/retriever.py, lexagent/tools/chunker.py, lexagent/nodes/cite.py
Phase 6 → lexagent/tools/raptor_summarizer.py, lexagent/tools/legal_kg.py, lexagent/tools/reranker.py
Phase 7 → lexagent/cli.py, lexagent/gateway/telegram.py
Phase 8 → lexagent/ui/, lexagent/tools/docx_writer.py
Phase 9 → lexagent/gateway/control_plane.py, lexagent/runtime/, lexagent/gateway/voice.py
```

---

## Prerequisites

You need Python installed and a terminal. That is all.

```bash
python --version   # anything 3.11+ is fine
```

Install the course dependencies (a small subset of what LexAgent uses):

```bash
cd "/Users/anshoosareen/Lexagent/course"
pip install pydantic pydantic-settings python-dotenv rich langgraph langchain-core litellm
```

Start with Phase 0.
