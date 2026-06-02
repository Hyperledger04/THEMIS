# Phase 5 — RAG and Retrieval: Grounded Citations

> **Status: Coming soon.** Complete Phases 0-4 first.

## What you will build

By the end of this phase, your agent will:
- Split case law text into parent/child chunks
- Score chunks using BM25 (exact keyword match) AND TF-IDF vector similarity
- Hybrid-rank them by combining both scores
- Ground every citation in the draft to a specific chunk
- Flag citations that don't match any source chunk as "unverified"

## The files you will understand

- `lexagent/tools/chunker.py` — parent/child chunking strategy
- `lexagent/tools/retriever.py` — `HybridRetriever`, BM25 + TF-IDF, `from_findings()`
- `lexagent/nodes/cite.py` — the citation verification node
- `lexagent/tools/query_expander.py` — Indian legal synonym expansion

## Key concepts

**Why RAG?** An LLM without RAG hallucinates citations. It makes up case names, citations, and holdings that sound plausible but are wrong. RAG (Retrieval-Augmented Generation) gives the LLM real source text to reference.

**Why hybrid retrieval?** Two problems:
- BM25 (keyword) is excellent for exact Indian citation strings: "AIR 1978 SC 597"
- TF-IDF vector is excellent for doctrine queries: "right to personal liberty"
- Neither alone is good at both. Hybrid = best of both.

**Why parent/child chunks?**
- Child chunks (256 tokens) are small enough for precise scoring
- Parent chunks (1024 tokens) give the LLM enough context to understand the holding
- Score on child, send parent to LLM

**α weight**: `LexConfig.retriever_bm25_weight` (default 0.4) controls BM25 vs vector balance.

## Coming in this phase

1. `01_chunking.py` — parent/child chunking, why size matters
2. `02_bm25.py` — BM25 from first principles, why it beats TF-IDF for citations
3. `03_tfidf_vectors.py` — TF-IDF vectors, cosine similarity
4. `04_hybrid_retrieval.py` — combining BM25 and vector scores
5. `05_cite_node.py` — the full citation grounding pipeline
6. `exercises/ex01_build_chunker.py` — implement parent/child chunker
7. `exercises/ex02_build_retriever.py` — implement hybrid retrieval
