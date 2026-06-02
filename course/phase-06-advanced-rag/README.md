# Phase 6 — Advanced RAG: RAPTOR, GraphRAG, Re-ranker

> **Status: Coming soon.** Complete Phases 0-5 first.

## What you will build

By the end of this phase, your agent will:
- Build a hierarchy of summaries over research findings (RAPTOR)
- Extract legal entities and build a knowledge graph (GraphRAG)
- Re-rank retrieval results using a cross-encoder LLM call
- Expand Indian legal queries with domain synonyms

All features are OFF by default. Toggle them with env vars.

## The files you will understand

- `lexagent/tools/raptor_summarizer.py` — cluster → summarize → build tree
- `lexagent/tools/legal_kg.py` — `extract_entities()`, `GraphRAGRetriever`
- `lexagent/tools/reranker.py` — `LLMReranker`, cross-encoder re-ranking
- `lexagent/tools/query_expander.py` — Indian legal synonym tables

## Key concepts

**RAPTOR** (Recursive Abstractive Processing for Tree-Organized Retrieval):
Group related research findings into clusters, then generate a summary for each cluster.
When answering a broad doctrine question, query the summaries instead of raw chunks.
Cost: one extra LLM call per cluster. Toggle: `LEX_RAPTOR_ENABLED=true`.

**GraphRAG** (Knowledge Graph RAG):
Extract entities (parties, courts, statutes, dates) from research findings.
Build a graph: Maneka Gandhi → cites → Kharak Singh; Article 21 → interpreted by → both.
Answer "what cases discuss Article 21 personal liberty?" using graph traversal, not just text search.
Toggle: `LEX_GRAPHRAG_ENABLED=true`.

**LLM Re-ranker**:
After retrieval, ask the LLM: "Given this query and this chunk, how relevant is it? Score 0-10."
Better than cosine similarity for legal text because the LLM understands doctrine.
Cost: one LLM call per retrieved chunk. Toggle: `LEX_RERANKER_ENABLED=true`.

## Coming in this phase

1. `01_raptor.py` — clustering, summarization, tree structure
2. `02_graphrag.py` — entity extraction, graph construction, traversal
3. `03_reranker.py` — cross-encoder re-ranking with an LLM
4. `04_query_expansion.py` — Indian legal synonyms and why they matter
5. `exercises/ex01_build_raptor_tree.py`
6. `exercises/ex02_extract_entities.py`
