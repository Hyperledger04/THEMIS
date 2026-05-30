# Phase 4 — Tools, Research & Citation Verification

## What Was Built

Phase 4 wires real Indian legal data into the LangGraph flow. After intake completes, the agent now researches Indian Kanoon, checks limitation periods, and verifies every citation in the draft before the graph ends.

---

## Graph Flow (Post Phase 4)

```
intake → research → draft → cite → END
  ↑          |
  └──────────┘  (loops until intake_complete=True)
```

**Before Phase 4:** `intake → draft → END`
**After Phase 4:** `intake → research → draft → cite → END`

---

## Files Created

### `lexagent/tools/registry.py` — ToolRegistry

Decorator-based self-registration system. Dropping a new `.py` file in `lexagent/tools/` and decorating a function with `@ToolRegistry.register(...)` is all it takes to add a tool.

```python
@ToolRegistry.register(name="my_tool", description="...")
def my_tool(...) -> dict: ...
```

Key methods:
- `ToolRegistry.get(name)` — retrieve a tool by name
- `ToolRegistry.list_names()` — list all registered tools
- `ToolRegistry.get_langchain_tools()` — return `StructuredTool` objects for `bind_tools()`

### `lexagent/tools/limitation.py` — Limitation Act Calculator

Registered as `"check_limitation"` tool. Looks up limitation periods under the Indian Limitation Act 1963.

| Matter Type | Period | Legal Basis |
|---|---|---|
| civil suit | 3 years | Article 113 |
| money recovery | 3 years | Article 36 |
| injunction | 3 years | Article 58 |
| property suit | 12 years | Article 65 |
| cheque dishonour | 1 year | S.138 NI Act |
| consumer complaint | 2 years | S.69 CPA 2019 |
| writ petition | None (laches) | Court discretion |
| legal notice | N/A | Pre-litigation |

**Risk output:** `expired` / `within_6_months` / `clear` / `unknown`

Deadline uses calendar-year arithmetic (not `timedelta(days=365*n)`) — legally correct and handles Feb 29 edge cases.

### `lexagent/nodes/research.py` — Research Node

Runs after `intake` completes. Builds an Indian Kanoon search query from intake fields (`matter_type + purpose + jurisdiction`), dispatches to the configured backend, and runs the limitation check.

**Backend modes** (set via `LEX_KANOON_BACKEND`):
- `stub` — returns a mock result, no browser required (default; used in tests and offline dev)
- `playwright` — launches real headless Chrome, scrapes Indian Kanoon

**State output:**
```python
{
    "research_findings": [{"title", "url", "snippet", "full_text", "citations_found", "status"}],
    "statutes_cited": ["CPC Order XXXIX Rule 1&2", ...],   # up to 15
    "limitation_analysis": "Limitation: 3 year(s) under Article 113...",
}
```

### `lexagent/nodes/cite.py` — Cite Node

Runs after `draft` when `auto_verify_citations=True` (default). Extracts Indian legal citations from the draft text using regex, then cross-references them against the fetched judgment corpus from `research_findings`.

**Citation formats matched:**
- `AIR YYYY SC/Bom/Del/... NNN`
- `(YYYY) N SCC NNN`
- `YYYY (N) SCC NNN`
- `YYYY SCC (L&S) NNN`
- `YYYY SCR NNN`
- `(YYYY) N MLJ NNN`

**State output:**
```python
{
    "citations_verified": True,   # False if any unverified remain
    "unverified_citations": None, # or list of unverified citation strings
}
```

---

## Graph Changes (`lexagent/graph.py`)

### `route_after_intake`
```python
# Before: return "draft"
# After:
if state.get("intake_complete"):
    return "research"   # ← Phase 4
```

### `route_after_draft`
```python
# Before: return END
# After:
config = LexConfig()
if config.auto_verify_citations and state.get("research_findings"):
    return "cite"
return END
```

### New nodes and edges
```python
graph.add_node("research", research.run)
graph.add_node("cite", cite.run)
graph.add_edge("research", "draft")   # research always feeds draft
graph.add_edge("cite", END)           # cite is terminal in Phase 4
```

---

## Config (`lexagent/config.py`) — Phase 4 Relevant Fields

| Field | Default | Env Var | Purpose |
|---|---|---|---|
| `kanoon_backend` | `"stub"` | `LEX_KANOON_BACKEND` | `stub` / `playwright` |
| `kanoon_headless` | `False` | `LEX_KANOON_HEADLESS` | Watch browser or run silently |
| `kanoon_max_results` | `3` | `LEX_KANOON_MAX_RESULTS` | Judgments fetched per search |
| `auto_verify_citations` | `True` | `LEX_AUTO_VERIFY_CITATIONS` | Toggle cite node on/off |

---

## Tests Added (44 new, 132 total passing)

| File | Tests | What is covered |
|---|---|---|
| `tests/test_registry.py` | 7 | Registration, retrieval, LangChain tool output |
| `tests/test_limitation.py` | 13 | All matter types, deadline arithmetic, risk flags |
| `tests/test_research.py` | 10 | Query building, stub backend, statute extraction, error capture |
| `tests/test_cite.py` | 14 | Citation regex (AIR, SCC, SCR, MLJ), verification logic, node contract |

---

## LexState Fields Activated

| Field | Type | Set by |
|---|---|---|
| `research_findings` | `Optional[List[dict]]` | research node |
| `statutes_cited` | `Optional[List[str]]` | research node |
| `limitation_analysis` | `Optional[str]` | research node |
| `citations_verified` | `bool` | cite node |
| `unverified_citations` | `Optional[List[str]]` | cite node |

---

## Phase 4 Checkpoint

> **Citations verified against Indian Kanoon** ✓

Run `lex draft "security deposit eviction Delhi"` with `LEX_KANOON_BACKEND=playwright` to see the full pipeline: intake → research (live Kanoon scrape) → draft → cite (verified against fetched judgments).

---

## Next: Phase 5

Phase 5 adds RAGFlow-inspired retrieval quality:
- **5a** — Laws-template chunker (`lexagent/tools/chunker.py`)
- **5b** — Hybrid BM25 + vector retrieval (`lexagent/tools/retriever.py`)
- **5c** — Chunk-level citation grounding (extend `cite.py`, add `grounded_citations` to LexState)
- **5d** — Child chunk hierarchy (small chunks for scoring, parent chunks for LLM context)
- **5e** — Review node + `.docx` output (`lexagent/nodes/review.py`, `lexagent/tools/docx_writer.py`)
