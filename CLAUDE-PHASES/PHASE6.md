# Phase 6: RAGFlow-Inspired Retrieval Upgrades

## Status

**Complete.** 245 tests passing (58 new Phase 6 tests + 187 carried forward from Phases 1–5).
All Phase 6 features are **off by default** — enabled via environment variable toggles so the standard `lex draft` flow is unchanged.

---

## What Phase 6 Added (Plain English)

Phase 5 built a basic search engine inside LexAgent: split documents into chunks, score them with BM25 + TF-IDF, return the best matches to the draft node.

Phase 6 adds five quality-of-life upgrades to that search engine, all inspired by how the open-source RAGFlow platform handles legal documents:

---

## Sub-phases

### 6a — PDF Parsing (`lexagent/tools/chunker.py`)

**Problem:** Lawyers receive judgment PDFs all the time. The Phase 5 chunker only handled plain text and DOCX.

**What was added:** `_extract_pdf_text()` inside `chunker.py`. It uses the `pdfplumber` library to open a PDF page by page and pull out the text while preserving reading order. Two special cases are handled:

- **Footnotes** — Indian judgments put citation references in small font at the bottom of the page. The code detects text in the bottom 15% of the page with font size ≤ 8pt and keeps it alongside the body text so citation matching still works.
- **Tables** — Any table on the page (e.g., a comparative statute table) is converted to Markdown format so the chunker treats it like structured text rather than garbled characters.

**Config flag:** `LEX_PDF_OCR_FALLBACK=true` enables Tesseract OCR for scanned (image-only) PDFs. Off by default because it needs an extra system dependency.

---

### 6b — Query Expansion (`lexagent/tools/query_expander.py`)

**Problem:** A lawyer types "injunction" but the judgment uses "ad interim stay." BM25 scores exact word matches — it misses this even though both mean the same thing.

**What was added:** `expand_query()`. Before running BM25, the query is expanded using a curated map of ~80 Indian legal synonyms. For example:

- `"injunction"` → also searches for `"stay"`, `"ad interim stay"`
- `"petitioner"` → also searches for `"applicant"`, `"appellant"`, `"writ petitioner"`
- `"air"` → also searches for `"all india reporter"`, `"AIR"`
- `"res judicata"` → also searches for `"issue estoppel"`, `"constructive res judicata"`

A generic ML model would get these Indian legal terms wrong; a handcrafted map is more precise.

A companion function `weight_terms()` gives higher BM25 weight to distinctively legal terms (`"SCC"`, `"specific performance"`, `"locus standi"`) so rare but important terms are not drowned out by common words.

**Config flag:** `LEX_QUERY_EXPANSION=true` (on by default).

---

### 6c — RAPTOR Hierarchical Summaries (`lexagent/tools/raptor_summarizer.py`)

**Problem:** When a matter has 10+ case findings, the LLM draft node receives all of them as-is. The LLM then has to work out the legal doctrine common across them on its own, which is error-prone and verbose.

**What was added:** `RaptorSummarizer`. It does this in three steps:

1. **Chunk** all research findings into small pieces using the Phase 5 chunker.
2. **Cluster** the pieces by legal similarity using TF-IDF cosine distance + hierarchical clustering (AgglomerativeClustering). Similar pieces go into the same bucket.
3. **Summarize** each bucket in 2–3 sentences using the LLM: *"What legal principle do all these passages share?"*

These doctrinal summaries are injected back into `research_findings` as synthetic entries (marked `source: "raptor_summary"`). The draft node now receives both the individual case snippets *and* concise doctrinal overviews — reducing the work it has to do.

Up to `raptor_max_layers=2` levels of clustering are supported: summaries of summaries, for very large finding sets.

**Config flags:** `LEX_RAPTOR_ENABLED=true` (off by default — costs one extra LLM call per cluster), `LEX_RAPTOR_MAX_LAYERS`, `LEX_RAPTOR_MAX_CLUSTER_SIZE`.

---

### 6d — GraphRAG: Legal Entity Knowledge Graph (`lexagent/tools/legal_kg.py`)

**Problem:** Research findings mention the same case, statute, and doctrine repeatedly across different sources. There was no way to answer "which cases cite Section 138 NI Act?" or "which judgments invoke natural justice together?"

**What was added:** `LegalKnowledgeGraph`. It reads through all research findings and extracts six types of legal entities using regex patterns (no ML model needed):

| Entity Type | Examples |
|-------------|----------|
| `CITATION` | `AIR 1978 SC 597`, `(2021) 5 SCC 143` |
| `STATUTE` | `Section 138 of the NI Act`, `Article 21 of the Constitution` |
| `COURT` | `Supreme Court of India`, `High Court of Bombay`, `NCLT` |
| `JUDGE` | `Justice Chandrachud`, `Honourable Justice K.S. Puttaswamy` |
| `PARTY` | Names on either side of "v." or "versus" |
| `DOCTRINE` | `res judicata`, `locus standi`, `natural justice`, `mens rea` |

When two entities appear in the same document, an edge is added between them with relation `"co-occurs"`. The resulting graph answers questions like "what other entities appear alongside 'res judicata' in this research?"

The graph is saved to SQLite so it persists between sessions and can be loaded for a returning matter.

**Config flag:** `LEX_GRAPHRAG_ENABLED=true` (off by default — adds an entity-extraction pass over all findings).

---

### 6e — LLM Re-ranker (`lexagent/tools/reranker.py`)

**Problem:** The hybrid BM25+TF-IDF retriever returns the top candidates by score, but BM25/TF-IDF scores only measure keyword overlap — not whether the passage actually *answers* the legal question.

**What was added:** `LLMReranker`. After retrieval gives back, say, 10 candidate passages, the re-ranker sends them all in a single LLM prompt asking: *"Rate each passage 0–10 for relevance to this legal query."* The passages are then re-sorted by that rating and only the top-k survivors reach the draft node.

This is the "cross-encoder" pattern: the LLM sees the query and the passage together, which is far more accurate than any score computed without the query.

It is wired into the retriever via `retrieve_reranked()` — a separate async method so existing synchronous callers are unaffected.

If the LLM call times out or returns unparseable output, the function falls back to the original retrieval order. The re-ranker is a quality boost, not a hard dependency.

**Config flag:** `LEX_RERANKER_ENABLED=true` (off by default — costs one extra LLM call per retrieval).

---

## New Files

| File | Purpose |
|------|---------|
| `lexagent/tools/query_expander.py` | Indian legal synonym map + query expansion |
| `lexagent/tools/raptor_summarizer.py` | Hierarchical cluster-then-summarize over research findings |
| `lexagent/tools/legal_kg.py` | Regex NER + knowledge graph + SQLite persistence |
| `lexagent/tools/reranker.py` | LLM cross-encoder re-ranker |
| `tests/test_query_expander.py` | 15 tests |
| `tests/test_raptor_summarizer.py` | 10 tests |
| `tests/test_legal_kg.py` | 20 tests |
| `tests/test_reranker.py` | 9 tests (+ 4 PDF tests added to `test_chunker.py`) |

## Modified Files

| File | Change |
|------|--------|
| `lexagent/tools/chunker.py` | Added `_extract_pdf_text()` and `_extract_page()` for Phase 6a |
| `lexagent/tools/retriever.py` | Added `retrieve_reranked()` async method wiring in LLMReranker |
| `lexagent/config.py` | Added 7 new Phase 6 feature-flag fields (`pdf_ocr_fallback`, `query_expansion_enabled`, `raptor_*`, `graphrag_enabled`, `reranker_enabled`) |

---

## Feature Flag Summary

All Phase 6 features are env-var controlled. Default state and cost:

| Feature | Env Var | Default | Extra Cost |
|---------|---------|---------|------------|
| PDF parsing | `LEX_PDF_OCR_FALLBACK` | OCR off, pdfplumber always on | None (pdfplumber is fast) |
| Query expansion | `LEX_QUERY_EXPANSION` | **On** | None (pure Python, no LLM) |
| RAPTOR summaries | `LEX_RAPTOR_ENABLED` | Off | ~1 LLM call per cluster |
| GraphRAG | `LEX_GRAPHRAG_ENABLED` | Off | CPU-only regex pass |
| LLM re-ranker | `LEX_RERANKER_ENABLED` | Off | 1 LLM call per retrieval |

---

## Key Design Decisions

- **No ML models in Phase 6.** PDF parsing uses pdfplumber (rule-based). Query expansion uses a handcrafted synonym map. Entity extraction uses regex. Clustering uses TF-IDF + sklearn. The only LLM calls are RAPTOR summarization and re-ranking, both off by default.
- **Everything off by default.** A lawyer running `lex draft "..."` gets identical behaviour to Phase 5. Features are opt-in. This avoids surprise latency or API cost increases.
- **Graceful degradation everywhere.** RAPTOR falls back to no summaries on empty findings. The re-ranker falls back to original order on any LLM error. PDF extraction raises a clear `ImportError` with install instructions if `pdfplumber` is missing.
- **Query expansion on by default** because it costs nothing (no LLM, no network) and measurably improves BM25 recall for Indian legal terminology.

---

## Next Phase

**Phase 7 — Telegram Gateway**

Build a Telegram bot that accepts a matter brief via `/draft`, runs the full LangGraph pipeline, and sends the formatted draft back in-chat. No web frontend — the bot is the interface.

Key files to create: `lexagent/gateway/telegram.py`, `lexagent/gateway/handlers.py`.
