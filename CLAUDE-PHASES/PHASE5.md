# Phase 5: RAGFlow-Inspired Retrieval

## Status

**Complete.** 187 tests passing (57 new Phase 5 tests + 130 carried forward from Phases 1-4).
One pre-existing failure in `test_kanoon.py::test_judgment_has_full_text` — Indian Kanoon changed their HTML structure; unrelated to Phase 5.

---

## What Phase 5 Added

Phase 5 replaced naive citation lookup with production-grade retrieval: structure-preserving chunking, hybrid BM25 + TF-IDF fusion, chunk-level citation grounding, parent/child context hierarchy, a validation gate node, and court-ready `.docx` output.

Graph flow after Phase 5:

```
intake → research → draft → cite → review → END
```

Previously `cite → END`. The `review` node is now mandatory; `.docx` is optional.

---

## Sub-phases

### 5a — Laws-Template Chunking (`lexagent/tools/chunker.py`)

Structure-preserving chunker for Indian legal documents. Splits on statutory headers (`Section X`, `Article X`, clauses `(a)`, `(i)`) — never breaks mid-clause across chunk boundaries. Handles plain text (DOCX and PDF ingestion can be piped in as text).

Each `Chunk` dataclass carries: `source_doc`, `section_id`, `chunk_index`, `chunk_text`, `parent_text`.

Fallback chain: statutory header split → paragraph split → word-boundary split (`_split_by_words()`). The word-boundary fallback handles the common case of a single oversized paragraph with no double-newlines.

### 5b — Hybrid BM25 + TF-IDF Retrieval (`lexagent/tools/retriever.py`)

Dual retrieval paths fused at rerank time:

- **BM25** (`rank-bm25`): exact keyword match — critical for Indian citation strings like `AIR 1978 SC 597` or `2021 SCC 143` that semantic search degrades on
- **TF-IDF vector similarity** (`scikit-learn`): semantic match for doctrine and concept queries

Fusion: `score = α * bm25_score + (1-α) * vector_score`, configurable via `LexConfig.retriever_bm25_weight` (default `0.4`).

`HybridRetriever.from_findings(findings)` builds both indexes from `research_findings` text. `.retrieve(query, top_k)` returns `RetrievalResult(child, parent, score, bm25_score, vector_score)`.

TF-IDF was chosen over sentence-transformers: lightweight, fully offline, no GPU required, and the retriever interface is stable — swapping in a dense encoder later is a one-file change.

BM25 empty corpus guard: `BM25Okapi([])` raises `ZeroDivisionError`. When the corpus is empty, `self._bm25 = None` and `retrieve()` returns `[]` instead of crashing.

### 5c — Chunk-Level Citation Grounding (`lexagent/nodes/cite.py` extension)

Every citation in `draft_output` is matched against a specific `chunk_id` from retrieval results — not just a case name string. The cite node populates `grounded_citations` in `LexState`:

```python
{
    "chunk_id": "AIR 1978 SC 597::0",   # source_doc::chunk_index
    "source": "AIR 1978 SC 597",
    "paragraph_ref": 1,
    "verified": True,
    "score": 0.87,
}
```

`citations_verified: bool` in `LexState` is only set `True` when every citation has a matching `chunk_id`. Unmatched citations go into `unverified_citations`.

### 5d — Child/Parent Chunk Hierarchy (`lexagent/tools/retriever.py`)

Small child chunks are used for precise match scoring; parent chunks are passed to the LLM for generation context. Configurable: `child_chunk_size=256` tokens, `parent_chunk_size=1024` tokens in `LexConfig`. The retriever returns `(child_chunk, parent_chunk)` pairs — only `parent_chunk` enters the LLM context window.

### 5e — Review Node + .docx Output

**`lexagent/nodes/review.py`** — Validation gate. Checks: all citations grounded, draft not empty, word count within jurisdiction limits. Word limits: injunction=5000, writ petition=8000, legal notice=2000, default=12000. Issues populate `risk_annotations`. If `docx_path` is set in state, calls `write_docx()` before returning.

**`lexagent/tools/docx_writer.py`** — Court-ready `.docx` via `python-docx`. 1.5" left margin, Times New Roman 12pt, double-spaced body paragraphs, justified alignment. Heading styles for matter type, parties, jurisdiction. Citations appendix with grounded/unverified status. Metadata footer with `matter_id`.

CLI: `lex draft "matter brief" --output draft.docx`

---

## New Files

| File | Purpose |
|------|---------|
| `lexagent/tools/chunker.py` | Laws-template structure-preserving chunker |
| `lexagent/tools/retriever.py` | Hybrid BM25 + TF-IDF retriever with parent/child hierarchy |
| `lexagent/nodes/review.py` | Validation gate — runs after cite, before END |
| `lexagent/tools/docx_writer.py` | Court-ready `.docx` formatter |
| `tests/test_chunker.py` | 16 tests |
| `tests/test_retriever.py` | 17 tests |
| `tests/test_review.py` | 14 tests |
| `tests/test_docx_writer.py` | 10 tests |

## Modified Files

| File | Change |
|------|--------|
| `lexagent/state.py` | Added `retrieval_chunks`, `grounded_citations`, `docx_path` fields |
| `lexagent/config.py` | Added `retriever_bm25_weight=0.4`, `retriever_similarity_threshold=0.35`, `child_chunk_size=256`, `parent_chunk_size=1024` |
| `lexagent/graph.py` | Added `review` node; rewired `cite → review → END` (was `cite → END`); `route_after_draft` now returns `"review"` |
| `lexagent/cli.py` | Wired `--output` flag to `docx_path` in initial state; added Phase 5 display panels (grounded citations count, docx path) |
| `lexagent/nodes/cite.py` | Extended with `HybridRetriever` grounding; per-citation chunk lookup; `citations_verified` only `True` when all citations matched |

---

## New LexState Fields

| Field | Type | Purpose |
|-------|------|---------|
| `retrieval_chunks` | `Optional[List[dict]]` | Raw retrieved chunks from hybrid retriever |
| `grounded_citations` | `Optional[List[dict]]` | Chunk-level citation grounding records |
| `docx_path` | `Optional[str]` | Path to generated `.docx` file, if requested |

---

## New Dependencies (`pyproject.toml`)

```
rank-bm25>=0.2
scikit-learn>=1.4
numpy>=1.26
python-docx>=1.1
```

---

## Key Design Decisions

- **TF-IDF over sentence-transformers**: offline, no GPU, zero cold-start. The retriever interface is stable — a dense encoder can replace it without touching the cite node or graph.
- **BM25 empty corpus guard**: `BM25Okapi([])` raises `ZeroDivisionError` at score time. Guard sets `self._bm25 = None`; `retrieve()` short-circuits to `[]`. This matters on matters with no research findings.
- **`_split_by_words()` fallback**: Indian statutes often have single-paragraph preambles that exceed `max_tokens` with no double-newlines. Without this fallback, the chunker produces one chunk larger than the configured limit.
- **Review node always runs**: `draft → review` edge is unconditional. `.docx` writing is conditional on `docx_path` being set. This keeps the validation path mandatory while making file output opt-in.

---

## Next Phase

**Phase 6 — Telegram Gateway**

Build a Telegram bot that accepts a matter brief as a message, runs the full LangGraph pipeline, and returns the draft (and optionally the `.docx`) back to the lawyer in-chat. No frontend — bot is the interface.

Key files to create: `lexagent/gateway/telegram.py`, `lexagent/gateway/handlers.py`.
Checkpoint: bot accepts brief via `/draft`, returns formatted draft in ≤60 seconds.
