# LexAgent Retrieval Evolution Roadmap — Phase 6 Through Phase 10

---

## Phase Comparison Table

| Phase | Strategy | Index Type | Data Sources | New Config Flags | Citation Accuracy (qualitative) |
|-------|----------|-----------|-------------|-----------------|-------------------------------|
| **6 (current)** | BM25+TF-IDF hybrid, RAPTOR (off), GraphRAG (off), LLM re-ranker (dead code) | In-memory BM25 + TF-IDF per session | Indian Kanoon (playwright or stub) | 13 existing flags | POOR — CRIT-01 threshold bypass; re-ranker never activates; RAPTOR crashes |
| **7** | BM25+TF-IDF hybrid (CRIT-01 fixed), re-ranker actually wired, precedent cache, query expansion fixed (MED-03) | In-memory + SQLite precedent cache | Indian Kanoon (API mode added), precedent_cache table | `LEX_PRECEDENT_CACHE_ENABLED`, `LEX_KANOON_API_KEY` | FAIR — hallucination floor raised; cached citations re-used without re-fetch |
| **8** | Hybrid + real OCR + statute index | In-memory + SQLite statute_case_index + precedent_cache | Indian Kanoon, uploaded PDFs (real OCR), matter documents | `LEX_OCR_ENABLED`, `LEX_STATUTE_INDEX_ENABLED`, `LEX_OCR_MIN_CHARS_PER_PAGE` | GOOD — scanned Indian court docs readable; statute-specific lookup supplements general search |
| **9** | Hierarchical PageIndex + citation chain graph + ratio extraction | 3-level SQLite index (doc→section→para) + citation_graph table | Kanoon, uploaded PDFs, prior matter cache, entity graph | `LEX_HIERARCHICAL_INDEX`, `LEX_CITATION_CHAIN_ENABLED`, `LEX_EXTRACT_RATIO`, `LEX_SECTION_CONTEXT_TOKENS` | VERY GOOD — parent context assembly prevents misattribution; overruled citations flagged |
| **10** | All Phase 9 + cross-matter learning + contradiction detection | Phase 9 indexes + audit trail integration | Phase 9 + workspace-scoped multi-matter corpus | `LEX_CROSS_MATTER_RAG`, `LEX_CONTRADICTION_CHECK` | EXCELLENT — contradiction flagged before review; ratio vs obiter distinguished |

---

## Detailed Phase Specifications

### Phase 7 Retrieval Changes

**What changes:**

1. **CRIT-01 fix** — In `tools/retriever.py` lines 145–151, the threshold bypass now returns `verified=False` instead of returning an unfiltered match as verified. In `cite.py`, the score check is:
   ```python
   # cite.py — after retrieve() call
   if results and results[0].score >= cfg.retriever_similarity_threshold:
       grounded.append({..., "verified": True, "score": results[0].score})
   else:
       unverified.append(cite)
   ```
   This change alone raises the citation accuracy floor from POOR to FAIR.

2. **Re-ranker actually wired** (HIGH-01 fix) — `cite.py` checks `cfg.reranker_enabled` and calls `retrieve_reranked()` instead of `retrieve()`:
   ```python
   # cite.py — in the citation loop
   if cfg.reranker_enabled:
       results = await retriever.retrieve_reranked(cite, top_k=3, llm=get_llm(cfg))
   else:
       results = retriever.retrieve(cite, top_k=1)
   ```
   This makes `LEX_RERANKER_ENABLED=true` have an actual effect for the first time.

3. **MED-03 fix** — `query_expander.py` duplicate "respondent" key merged. `weight_terms()` either removed or wired into `_bm25_scores()`.

4. **Precedent cache** — New SQLite table in `sessions.db`:
   ```sql
   CREATE TABLE IF NOT EXISTS precedent_cache (
       citation TEXT PRIMARY KEY,
       case_name TEXT,
       court TEXT,
       decision_date TEXT,
       full_text TEXT,
       fetched_at TEXT
   );
   ```
   Research node checks cache before Kanoon: `SELECT * FROM precedent_cache WHERE citation = ?`.
   On cache miss: fetch from Kanoon, insert into cache.

5. **Kanoon API backend** — Add `kanoon_backend="api"` path using the Indian Kanoon REST API (`https://api.indiankanoon.org/`) with `kanoon_api_key`. This eliminates the Playwright browser startup latency (2–4 sec) and is required for Phase 9 citation chain traversal.

**New config flags for Phase 7:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_PRECEDENT_CACHE_ENABLED` | `True` | Check/write citation cache in sessions.db |
| `LEX_KANOON_API_KEY` | `None` | Enables `kanoon_backend="api"` path |

---

### Phase 8 Retrieval Changes

**What changes:**

1. **OCR fallback actually implemented** (HIGH-02 fix):

In `tools/chunker.py:_extract_pdf_text()`:
```python
# chunker.py — add after pdfplumber extraction
def _extract_pdf_text(path: Path) -> str:
    text = _extract_with_pdfplumber(path)
    cfg = LexConfig()
    if cfg.pdf_ocr_fallback:
        pages = list(pdfplumber.open(path).pages)
        avg_chars = len(text) / max(len(pages), 1)
        # WHY: Indian scanned court documents have < 100 chars/page from pdfplumber
        # (it extracts empty boxes). If avg_chars below threshold, fall back to OCR.
        if avg_chars < cfg.ocr_min_chars_per_page:
            text = _extract_with_tesseract(path)  # new function
    return text

def _extract_with_tesseract(path: Path) -> str:
    import pytesseract
    from PIL import Image
    import fitz  # PyMuPDF for rendering pages to images
    doc = fitz.open(str(path))
    pages_text = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # WHY: lang="hin+eng" handles Hindi text in Indian court orders
        pages_text.append(pytesseract.image_to_string(img, lang="hin+eng"))
    return "\n".join(pages_text)
```

2. **Statute-to-case index**:

New SQLite table written by research node after each Kanoon fetch:
```sql
CREATE TABLE IF NOT EXISTS statute_case_index (
    statute     TEXT,
    section     TEXT,
    case_name   TEXT NOT NULL,
    citation    TEXT,
    relevance   TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (statute, section, citation)
);
```

Research node extracts statute references using the existing `_STATUTE_RE` and writes to this table.

New tool `query_statute_index` queries by statute+section before falling back to Kanoon search:
```python
@ToolRegistry.register(name="query_statute_index", ...)
def query_statute_index(statute: str, section: str) -> List[dict]:
    # Returns cached cases interpreting this statute section
    ...
```

**New config flags for Phase 8:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_OCR_ENABLED` | `False` | Enables pytesseract OCR path (requires tesseract binary) |
| `LEX_OCR_MIN_CHARS_PER_PAGE` | `100` | Threshold below which OCR fallback triggers |
| `LEX_STATUTE_INDEX_ENABLED` | `True` | Write fetched cases to statute_case_index table |

---

### Phase 9 Retrieval Changes

**What changes:**

1. **PageIndex 3-level hierarchical index:**

The `Chunk` dataclass in `chunker.py` is extended:
```python
# chunker.py — Chunk dataclass extension
@dataclass
class Chunk:
    # Existing fields
    source_doc: str
    chunk_index: int
    chunk_text: str        # child chunk (256 tokens)
    parent_text: str       # parent chunk (1024 tokens)
    section_id: str
    # NEW Phase 9 fields
    section_title: str     # human-readable section heading
    document_summary: str  # 2-sentence doc-level summary (pre-computed)
    hierarchy_path: str    # "doc_id/section_id/chunk_id" — full path
```

Retrieval assembles context at 3 levels:
```
Query → BM25+TF-IDF → child chunk match
                    → parent section text (1024 tokens)
                    → document summary (injected as metadata)
```

The `HybridRetriever.retrieve()` return type is extended to include `section_title` and `document_summary` in `RetrievalResult`.

This requires a one-time chunker rewrite for existing research findings. New `from_findings()` call computes document summaries via RAPTOR (if enabled) or a lightweight first-100-words heuristic.

2. **Citation chain graph:**

New SQLite table:
```sql
CREATE TABLE IF NOT EXISTS citation_graph (
    citation    TEXT NOT NULL,
    cites       TEXT NOT NULL,
    relationship TEXT,    -- "cites", "overrules", "distinguishes", "followed"
    source_url  TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (citation, cites)
);
```

New tool `trace_citation_chain` traverses this graph:
```python
# tools/citation_chain.py
def trace_citation_chain(
    citation: str,
    max_depth: int = 3,
    db_path: str = "~/.lexagent/sessions.db"
) -> dict:
    # BFS traversal of citation_graph table
    # Returns: {chain: [{citation, cites, relationship}], overruled: bool}
    ...
```

Citation chain is populated by the Kanoon API fetch — each judgment's "Cited in" section is parsed to extract citing cases and relationships.

3. **Ratio decidendi extraction:**

After each Kanoon fetch in research node (when `LEX_EXTRACT_RATIO=true`):
```python
# research.py — post-fetch LLM pass (inline, not a new node)
async def _extract_ratio(text: str, case_name: str, llm) -> dict:
    # Single LLM call with structured output
    # Returns: {ratio: str, obiter: List[str], holding: str}
    ...
```

`research_findings` dict extended with `ratio`, `obiter`, `is_obiter_dominated`.

Draft node instruction builder updated to use `ratio` instead of `snippet` for "Verified case law":
```python
# draft.py — in build_draft_instruction()
for r in research:
    if r.get("is_raptor"):
        continue  # CRIT-02 fix: never inject RAPTOR as verified case law
    citation_text = r.get("ratio") or r.get("relevance") or r.get("snippet") or ""
    instruction += f"- {r['case_name']} ({r.get('citation', 'N/A')}): {citation_text}\n"
```

**New config flags for Phase 9:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_HIERARCHICAL_INDEX` | `False` | 3-level index in chunker + retriever |
| `LEX_SECTION_CONTEXT_TOKENS` | `512` | Tokens from parent section to include |
| `LEX_CITATION_CHAIN_ENABLED` | `False` | Build and traverse citation_graph table |
| `LEX_CITATION_CHAIN_MAX_DEPTH` | `3` | Max BFS depth for chain traversal |
| `LEX_EXTRACT_RATIO` | `False` | LLM ratio/obiter extraction per judgment |

---

### Phase 10 Retrieval Changes

**What changes:**

1. **Cross-matter RAG** — When `workspace_id` is set, the research node can search precedent_cache and statute_case_index across all matters in the workspace, not just the current matter.

New config flag: `LEX_CROSS_MATTER_RAG` (bool, default False — privacy concern: junior lawyer should not see senior's matter content without explicit workspace grant).

2. **Contradiction detection integration** — The `contradiction_check` node uses the same `HybridRetriever` that cite uses, but queries with the draft argument text instead of the citation string. If it finds a chunk from the cited case that contradicts the argument, it returns `contradiction_flags`.

3. **Confidence scoring on retrieval** — Each `RetrievalResult` now carries a `confidence` value (0–1) derived from:
   - BM25 score normalized by max score in corpus
   - TF-IDF cosine score
   - Re-ranker score (if enabled)
   - Chain graph relationship (cited: +0.1, overruled: -0.5, distinguished: -0.2)
   - Ratio vs obiter (ratio: no change, obiter: -0.3)

**New config flags for Phase 10:**

| Flag | Default | Effect |
|------|---------|--------|
| `LEX_CROSS_MATTER_RAG` | `False` | Search workspace-wide precedent cache |
| `LEX_CONTRADICTION_CHECK` | `False` | Run contradiction check node |
| `LEX_CONFIDENCE_SCORING` | `True` | Attach confidence scores to citations |

---

## PageIndex Design — Data Structures

### Index Layout

```
Document (source_doc)
    |
    +-- Section (section_id, section_title)
    |       |
    |       +-- Paragraph/Chunk (chunk_index, chunk_text 256 tokens)
    |       |       |
    |       |       +-- [BM25 score, TF-IDF score, fused_score]
    |       |
    |       +-- [parent_text 1024 tokens — the full section]
    |
    +-- [document_summary — 2 sentences, pre-computed]
```

### Query Expansion Flow (Phase 7+)

```
User query string
      |
      v
expand_query() -- Indian legal synonyms from LEGAL_SYNONYMS dict
      |           (MED-03 duplicate key fixed)
      v
expanded_query (list of terms)
      |
      +--------> BM25Okapi.get_scores(expanded_query)
      |
      +--------> TF-IDF transform + cosine_similarity
      |
      v
fused_scores = 0.4 * bm25 + 0.6 * tfidf
      |
      v  (CRIT-01 fix applied)
threshold_filter: fused >= LEX_SIMILARITY_THRESHOLD (0.35)
      |
      v  (if LEX_RERANKER_ENABLED=true)
LLMReranker.rerank(query, candidates)
      |
      v
top_k results with {child_text, parent_text, section_title, document_summary, score, confidence}
```

---

## Citation Chain Graph Design

### Graph Schema

```
Nodes: {citation_string} — normalized Indian citation format
Edges: {relationship} — "cites", "overrules", "distinguishes", "followed", "affirmed"

Example:
  "AIR 1978 SC 597" --[cites]--> "AIR 1963 SC 1206"
  "2021 SCC 452"    --[overrules]--> "AIR 1978 SC 597"
  "2023 HC Del 445" --[followed]--> "AIR 1978 SC 597"
```

### Storage

SQLite `citation_graph` table (schema above). No separate graph DB — networkx is used for
in-memory traversal during a graph run:

```python
# tools/citation_chain.py
import networkx as nx

def load_citation_graph(db_path: str) -> nx.DiGraph:
    # Loads all edges from citation_graph table into a networkx DiGraph
    # WHY: networkx provides BFS/DFS traversal without requiring a graph DB
    # service. For < 100K citations (realistic for a solo lawyer's career),
    # in-memory traversal is fast enough (< 100ms).
    ...

def is_overruled(citation: str, G: nx.DiGraph) -> bool:
    # Returns True if any successor node has relationship="overrules"
    for _, _, data in G.out_edges(citation, data=True):
        if data.get("relationship") == "overrules":
            return True
    return False
```

### Populating the Graph

Three mechanisms:
1. **Research node** — after fetching a judgment, parses "Cited Cases" section using regex; writes to `citation_graph`
2. **Cite node** — when a citation is verified, checks if it appears in `citation_graph`; if not, schedules a background fetch
3. **`lex cite-chain "AIR 1978 SC 597"`** — CLI command that forces a deep fetch for a specific citation

---

## Statute-to-Case Index Design

### Schema

```sql
CREATE TABLE statute_case_index (
    statute      TEXT NOT NULL,   -- e.g., "Indian Penal Code"
    section      TEXT NOT NULL,   -- e.g., "420"
    case_name    TEXT NOT NULL,
    citation     TEXT,
    relevance    TEXT,            -- one-line relevance note
    fetched_at   TEXT,
    PRIMARY KEY (statute, section, citation)
);
CREATE INDEX idx_statute_section ON statute_case_index(statute, section);
```

### Population

`tools/limitation.py:_STATUTE_RE` already extracts statute references. The same regex is used
post-fetch in `research.py` to write to `statute_case_index`.

### Query API

```python
# tools/statute_index.py
@ToolRegistry.register(name="query_statute_index", ...)
def query_statute_index(statute: str, section: str, top_k: int = 10) -> List[dict]:
    # Returns [{case_name, citation, relevance, fetched_at}]
    # Ordered by fetched_at DESC (most recent first — SC cases updated over time)
    ...
```

---

## Cross-Matter Precedent Cache Design

### Cache Key Design

```python
# WHY: The citation string is the canonical key.
# Indian citation formats (AIR, SCC, SCR) are normalized before storage.
# Normalization: remove extra spaces, uppercase court abbreviations.
def normalize_citation(citation: str) -> str:
    citation = re.sub(r'\s+', ' ', citation.strip())
    citation = citation.upper().replace(' SCC ', ' SCC ')
    return citation
```

### Eviction Policy

The cache has no automatic eviction in Phase 7. In Phase 9, add:
- TTL: 365 days (overruled cases are rare; stale precedent risk is low for Indian SC citations)
- Manual: `lex cache clear --precedents` CLI command
- `LEX_PRECEDENT_CACHE_TTL_DAYS` config flag (default 365)

### Privacy Boundary

With `LEX_CROSS_MATTER_RAG=False` (default), `precedent_cache` only stores citation text and metadata — not matter-specific analysis. The full_text of a judgment is public information (Indian Kanoon is public). There is no client PII in the precedent cache.

---

## Integration with `cite.py` and `retriever.py`

### Phase 7 Integration Changes

In `cite.py`, replace the current `if results:` check (CRIT-01 bug) with score-gated verification:

```python
# cite.py — replace lines 110-120
for cite_str in raw:
    if cfg.reranker_enabled:
        results = await retriever.retrieve_reranked(cite_str, top_k=3, llm=get_llm(cfg))
    else:
        results = retriever.retrieve(cite_str, top_k=1)

    # CRIT-01 fix: check score before marking verified
    if results and results[0].score >= cfg.retriever_similarity_threshold:
        grounded.append({
            "chunk_id": results[0].chunk_id,
            "source": results[0].source_doc,
            "paragraph_ref": results[0].section_id,
            "verified": True,
            "score": results[0].score
        })
    else:
        # Check precedent_cache as fallback before marking unverified
        cached = check_precedent_cache(cite_str, cfg.sessions_db)
        if cached:
            grounded.append({..., "verified": True, "score": 0.9, "source": "cache"})
        else:
            unverified.append(cite_str)
```

### Phase 9 Integration Changes

The `HybridRetriever.retrieve()` return type `RetrievalResult` is extended:

```python
# tools/retriever.py — RetrievalResult namedtuple extension
RetrievalResult = namedtuple(
    "RetrievalResult",
    ["chunk_id", "child", "parent", "score", "bm25_score", "vector_score",
     # Phase 9 additions:
     "section_title", "document_summary", "hierarchy_path", "confidence"]
)
```

All callers of `retrieve()` that access `RetrievalResult` fields must be updated when this change ships:
- `cite.py` (accesses `.child`, `.parent`, `.score`, `.bm25_score`, `.vector_score`)
- No other direct callers (retriever.py has no other callers per architecture_map.md)
