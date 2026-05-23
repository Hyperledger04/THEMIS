# LexAgent Retrieval Graph

Covers Phase 5 hybrid retrieval and Phase 6 RAGFlow-inspired extensions.

---

## Phase 5 vs Phase 6 Retrieval Pipeline Comparison

### Phase 5: Hybrid BM25 + TF-IDF

```
research_findings (list[dict])
        │
        ▼
HybridRetriever.from_findings()
        │
        ├─── chunk_text(full_text, max_tokens=256)  ──▶ child_chunks
        └─── chunk_text(full_text, max_tokens=1024) ──▶ parent_chunks
                │
                ▼
        BM25Okapi(tokenised_children)       TfidfVectorizer.fit_transform(child_texts)
                │                                    │
                └─────────────┬───────────────────────┘
                              │
                         retrieve(query, top_k)
                              │
                         ┌────▼────────────────────┐
                         │ bm25_scores = BM25Okapi  │
                         │ vector_scores = cosine   │
                         │ fused = α*bm25 + (1-α)*v │
                         │ filter >= threshold      │
                         └────────────┬────────────┘
                                      │
                              RetrievalResult(child, parent, score)
```

**Trigger:** `config.auto_verify_citations=True` AND `research_findings` is non-empty (via `route_after_draft`). Executed in the `cite` node.

**Data sources:** `research_findings` dicts built from Indian Kanoon scraper output. Fields used: `full_text` (primary), `header + snippet` (fallback if no `full_text`), `citation` or `case_name` (source label).

**Chunking method:** `tools/chunker.py:chunk_text()` — structure-preserving. Splits on statutory section headers (`_SECTION_RE`) first, then on paragraph boundaries for oversized sections, then on word boundaries as last resort. Token count approximated by whitespace split (`_approx_tokens`).

**Embedding model:** None. TF-IDF with `ngram_range=(1,2)` and `sublinear_tf=True`. This is a sparse vector — not a semantic embedding.

**BM25 variant:** `rank_bm25.BM25Okapi`

**Fusion weight:** `α=0.4` (BM25) + `0.6` (TF-IDF). Configurable via `LEX_BM25_WEIGHT`.

**Similarity threshold:** `0.35` (configurable via `LEX_SIMILARITY_THRESHOLD`). When nothing exceeds the threshold, the top_k results are returned without filtering (threshold bypass fallback).

---

### Phase 6 Extensions (all off by default)

| Feature | Config Flag | Default | File | How It Works |
|---------|-------------|---------|------|--------------|
| PDF parsing (pdfplumber) | `LEX_PDF_OCR_FALLBACK` | `False` | `tools/chunker.py:_extract_pdf_text()` | Layout-aware word extraction; footnote separation by y-coordinate; table serialisation to markdown |
| Query expansion | `LEX_QUERY_EXPANSION` | `True` | `tools/query_expander.py:expand_query()` | Appends Indian legal synonyms from `LEGAL_SYNONYMS` dict to BM25 query before tokenisation |
| RAPTOR | `LEX_RAPTOR_ENABLED` | `False` | `tools/raptor_summarizer.py` | Clusters research_findings chunks by TF-IDF cosine; LLM summarizes each cluster; summaries injected as synthetic research_findings |
| GraphRAG | `LEX_GRAPHRAG_ENABLED` | `False` | `tools/legal_kg.py` | Regex NER extracts 6 entity types; co-occurrence edges built; stored in `state["entity_graph"]` |
| LLM Reranker | `LEX_RERANKER_ENABLED` | `False` | `tools/reranker.py` | LLM rates (query, passage) pairs 0-10 in a single batched prompt; available via `retrieve_reranked()` |

**Note:** Query expansion (`LEX_QUERY_EXPANSION`) defaults to `True` unlike the other Phase 6 features. It is the only Phase 6 feature active in the default configuration.

---

## Feature Flag Table

| Env Var | Field in LexConfig | Default | Effect When Enabled |
|---------|-------------------|---------|---------------------|
| `LEX_KANOON_BACKEND` | `kanoon_backend` | `"stub"` | `"playwright"` triggers real browser scraping |
| `LEX_AUTO_VERIFY_CITATIONS` | `auto_verify_citations` | `True` | Routes draft → cite → review instead of draft → review |
| `LEX_QUERY_EXPANSION` | `query_expansion_enabled` | `True` | Passes expanded query to BM25 in HybridRetriever |
| `LEX_RAPTOR_ENABLED` | `raptor_enabled` | `False` | Runs RAPTOR tree build in research node; adds synthetic findings |
| `LEX_RAPTOR_MAX_LAYERS` | `raptor_max_layers` | `2` | Controls RAPTOR hierarchy depth |
| `LEX_RAPTOR_MAX_CLUSTER_SIZE` | `raptor_max_cluster_size` | `5` | Target max nodes per cluster |
| `LEX_GRAPHRAG_ENABLED` | `graphrag_enabled` | `False` | Runs entity extraction + KG build in research node |
| `LEX_RERANKER_ENABLED` | `reranker_enabled` | `False` | Config flag exists but is **NOT checked anywhere in the graph**; LLMReranker can only be invoked by callers using `retrieve_reranked()` |
| `LEX_PDF_OCR_FALLBACK` | `pdf_ocr_fallback` | `False` | Config flag exists but is **NOT checked in the chunker**; pdfplumber is always used for PDFs regardless |
| `LEX_BM25_WEIGHT` | `retriever_bm25_weight` | `0.4` | BM25 weight in fused score |
| `LEX_SIMILARITY_THRESHOLD` | `retriever_similarity_threshold` | `0.35` | Minimum fused score to include chunk |
| `LEX_CHILD_CHUNK_SIZE` | `child_chunk_size` | `256` | Max tokens per child chunk |
| `LEX_PARENT_CHUNK_SIZE` | `parent_chunk_size` | `1024` | Max tokens per parent chunk |

---

## Full Retrieval Data Flow (Phase 5 + 6)

```
User query (matter brief)
        │
        ▼
[Research Node]
        │
        ├─── query = matter_type + purpose[:150] + jurisdiction
        │
        ├─── IF kanoon_backend == "stub":
        │       stub result with placeholder text
        │
        └─── IF kanoon_backend == "playwright":
                Playwright → indiankanoon.org/search
                        │
                        └─ for each result:
                              _fetch_judgment() → full_text (capped 15k chars)
                                                  header, citations_found[]
                                                  
        │
        ├─── check_limitation(matter_type, cause_of_action_date)
        │       → limitation_analysis: str
        │
        ├─── _extract_statutes(results) via _STATUTE_RE
        │       → statutes_cited: list[str] (max 15)
        │
        ├─── [IF raptor_enabled]
        │       chunk_text(finding.full_text, max_tokens=256) → Chunks
        │       TF-IDF vectorize all chunk texts
        │       AgglomerativeClustering(n_clusters = len/max_cluster_size)
        │       asyncio.gather(summarize each cluster via LLM)
        │       raptor_tree_to_findings() → synthetic entries appended to research_findings
        │
        └─── [IF graphrag_enabled]
                for finding in results:
                    LegalKnowledgeGraph.add_text(full_text + snippet)
                    → regex NER: CITATION, STATUTE, COURT, JUDGE, PARTY, DOCTRINE
                    → co-occurrence edges built
                entity_graph = kg.to_dict()

[Route: draft → cite (if auto_verify_citations and research_findings)]

[Cite Node]
        │
        ├─── _extract_citations(draft_output) via _CITATION_RE
        │       → raw: list[str] (deduplicated Indian citation strings)
        │
        ├─── IF findings non-empty:
        │       HybridRetriever.from_findings(findings, ...)
        │               │
        │               ├─── chunk_text(body, max_tokens=256) → child_chunks
        │               ├─── chunk_text(body, max_tokens=1024) → parent_chunks
        │               ├─── BM25Okapi(tokenised_children)
        │               └─── TfidfVectorizer.fit_transform(child_texts)
        │
        │       for each citation:
        │           IF query_expansion_enabled:
        │               expand_query(cite) → expanded BM25 query
        │           bm25_scores = BM25Okapi.get_scores(expanded_query)
        │           vector_scores = cosine_similarity(vectorizer.transform([cite]), matrix)
        │           fused = 0.4*bm25 + 0.6*vector
        │           IF fused >= 0.35: top match → verified=True
        │           ELSE:            no match  → unverified_citations.append(cite)
        │
        └─── IF findings empty:
                fallback: " ".join(full_text + header + snippet for all findings)
                verified = [c for c in raw if c in corpus]
                unverified = [c for c in raw if c not in corpus]
```

---

## Known Retrieval Risks

### 1. Hallucination Vectors

| Risk | Location | Severity |
|------|----------|----------|
| LLM invents citations during drafting | `nodes/draft.py` — no citations in findings path | HIGH |
| Threshold bypass returns low-quality match as verified | `tools/retriever.py` lines 148-151 | HIGH |
| Stub mode: all drafts use placeholder research | `nodes/research.py` lines 70-78 | MEDIUM |
| RAPTOR synthetic entries have `citation=None` but appear in research_findings | `tools/raptor_summarizer.py:raptor_tree_to_findings()` | MEDIUM |
| Draft node injects RAPTOR summaries as "Verified case law" even though they have no real citation | `nodes/draft.py` line 158-161 | HIGH |

**Detail on threshold bypass (HIGH risk):** In `retriever.py` lines 145-151:
```python
indices = np.where(fused >= self._threshold)[0]
if len(indices) == 0:
    # Fall back to top_k without threshold
    indices = np.argsort(fused)[::-1][:top_k]
```
When nothing passes threshold, the top chunk (possibly near-zero score) is returned. In `cite.py` line 114, `if results:` is True, so the citation gets `verified=True` even though the score may be near zero. A citation can be marked verified against a completely unrelated chunk.

**Detail on RAPTOR injection (HIGH risk):** `raptor_tree_to_findings()` returns dicts with `citation=None`. The draft node checks `if research:` and then:
```python
instruction += "Verified case law to use:\n" + "\n".join(
    f"- {r['case_name']} ({r['citation']}): {r['relevance']}" for r in research
)
```
RAPTOR entries have `case_name="RAPTOR Summary (layer 1)"` and `citation=None`, so the draft sees `"RAPTOR Summary (layer 1) (None)"` listed as "Verified case law". The LLM may treat these as real citations.

### 2. Chunk Boundary Issues

- `_approx_tokens()` uses whitespace split (word count), not subword tokens. This underestimates by ~20% for legal text with long Latin phrases. A 256-"token" chunk may be 300+ actual tokens.
- `_split_by_words()` at line 252-257 of `chunker.py` creates hard word-boundary cuts with no overlap. If a citation string spans a word-boundary cut, the BM25 match may degrade.
- Section detection regex `_SECTION_RE` only matches Indian legislation patterns (`Section X`, `Article X`, `(a)`, `(i)`). For UK/US judgments or plain paragraphs, all text falls into `para_0` — one huge chunk that gets word-split.

### 3. Re-Ranker Bypass Conditions

The LLM re-ranker (`tools/reranker.py`) is never activated in the current graph:
- `config.reranker_enabled` is read nowhere in the graph
- `HybridRetriever.retrieve_reranked()` is never called (cite node uses synchronous `retrieve()`)
- The feature is effectively dead code despite the config flag existing

### 4. Query Expansion Issues

`LEGAL_SYNONYMS` in `query_expander.py` has a duplicate key (line 27 and 35): `"respondent"` appears twice. In Python dicts, the last definition wins, so the first definition (`["defendant", "opposite party", "non-applicant"]`) is silently overwritten by the second (`["appellee", "defendant", "opposite party"]`). This is a silent data bug.

The `weight_terms()` function in `query_expander.py` computes term weights but is never called anywhere in the codebase.

### 5. PDF OCR Fallback

`config.pdf_ocr_fallback` is defined but the chunker's `_extract_pdf_text()` always uses `pdfplumber` and never checks this flag. There is no Tesseract/pytesseract OCR path implemented despite the config field existing. Scanned PDFs will produce empty text silently.
