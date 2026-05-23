# Cite node: extracts citations from the draft, cross-references them against
# research_findings, and (Phase 5) grounds each citation to a specific chunk_id.
#
# Phase 5 extension:
#   - Builds a HybridRetriever from research_findings
#   - For each citation in the draft, retrieves the best-matching chunk
#   - Populates grounded_citations and retrieval_chunks in state
#   - citations_verified is only True when ALL citations have a chunk_id match

import asyncio
import re

from rich.console import Console

from lexagent.config import LexConfig
from lexagent.state import LexState

console = Console()

# WHY: Indian citation formats span several series (AIR, SCC, SCR, regional).
# BM25 handles exact string match better for grounding; regex here extracts
# the citation strings from the draft text to feed into retrieval.
_CITATION_RE = re.compile(
    r"(?<!\w)"
    r"("
    r"AIR\s+\d{4}\s+(?:SC|All|Bom|Cal|Mad|Del|Ker|Kar|MP|Raj|Guj|P&H)\s+\d+"
    r"|\(\d{4}\)\s+\d+\s+SCC\s+\d+"
    r"|\d{4}\s+\(\d+\)\s+SCC\s+\d+"
    r"|\d{4}\s+SCC\s+\(L&S\)\s+\d+"
    r"|\d{4}\s+SCR\s+\d+"
    r"|\(\d{4}\)\s+\d+\s+MLJ\s+\d+"
    r")"
)


def _extract_citations(text: str) -> list[str]:
    """Return a deduplicated list of Indian legal citation strings found in text."""
    return list({m.group(0) for m in _CITATION_RE.finditer(text)})


def _split_paragraphs(text: str) -> list[str]:
    """Split draft into paragraphs for paragraph_ref tracking."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _find_paragraph_ref(citation: str, paragraphs: list[str]) -> int:
    """Return the 1-based index of the paragraph that contains this citation."""
    for i, para in enumerate(paragraphs, start=1):
        if citation in para:
            return i
    return 0  # 0 = not found in any paragraph


def _verify_citations(
    raw: list[str],
    findings: list[dict],
) -> tuple[list[str], list[str]]:
    """
    Phase 4 fallback: verify citations by substring match in the corpus.
    Used when research_findings exist but the HybridRetriever returns nothing.
    """
    corpus = " ".join(
        r.get("full_text", "") + " " + r.get("header", "") + " " + r.get("snippet", "")
        for r in findings
    )
    verified: list[str] = []
    unverified: list[str] = []
    for cite in raw:
        (verified if cite in corpus else unverified).append(cite)
    return verified, unverified


async def run(state: LexState) -> dict:
    try:
        draft = state.get("draft_output") or ""
        findings = state.get("research_findings") or []

        raw = _extract_citations(draft)
        console.print(f"[bold blue]→ Cite:[/bold blue] {len(raw)} citation(s) in draft")

        if not raw:
            return {
                "citations_verified": True,
                "unverified_citations": None,
                "grounded_citations": [],
                "retrieval_chunks": [],
            }

        paragraphs = _split_paragraphs(draft)

        # ----------------------------------------------------------------
        # Phase 5 / Phase 9: chunk-level grounding via HybridRetriever
        # Phase 9: when Qdrant is enabled, augment in-session findings with
        # any prior-session findings stored in the persistent collection.
        # ----------------------------------------------------------------
        if findings:
            cfg = LexConfig()

            # Phase 9: pull extra findings from Qdrant to supplement current session.
            # WHY: matters accumulate knowledge across restarts; cite node should see all of it.
            qdrant_extra: list[dict] = []
            if cfg.qdrant_enabled and state.get("matter_id"):
                try:
                    from lexagent.tools.retriever import PersistentQdrantRetriever
                    firm_id = state.get("firm_id") or cfg.default_firm_id
                    qr = PersistentQdrantRetriever(state["matter_id"], firm_id=firm_id, cfg=cfg)
                    for raw_cite in raw:
                        qdrant_extra.extend(qr.retrieve(raw_cite, top_k=3))
                except Exception:
                    pass

            # Merge Qdrant results into findings (deduplicate by citation string).
            if qdrant_extra:
                existing_citations = {f.get("citation") for f in findings}
                for extra in qdrant_extra:
                    if extra.get("citation") not in existing_citations:
                        findings.append(extra)
                        existing_citations.add(extra.get("citation"))

            from lexagent.tools.retriever import HybridRetriever

            retriever = HybridRetriever.from_findings(
                findings,
                bm25_weight=cfg.retriever_bm25_weight,
                similarity_threshold=cfg.retriever_similarity_threshold,
                child_max_tokens=cfg.child_chunk_size,
                parent_max_tokens=cfg.parent_chunk_size,
                query_expansion=cfg.query_expansion_enabled,
            )

            # ----------------------------------------------------------------
            # Phase 6e: LLM re-ranker (optional, config-gated)
            # WHY: Build once outside the citation loop — one LLMReranker instance
            # is reused for every citation rather than constructing a new LLM
            # client per call.
            # ----------------------------------------------------------------
            reranker = None
            if cfg.reranker_enabled:
                from lexagent.nodes._llm import get_llm
                from lexagent.tools.reranker import LLMReranker
                reranker = LLMReranker(llm=get_llm(cfg), top_k=1)
                console.print("[cyan]→ Cite:[/cyan] LLM re-ranker enabled")

            grounded: list[dict] = []
            unverified: list[str] = []
            all_chunks: list[dict] = []

            loop = asyncio.get_event_loop()
            for cite in raw:
                # WHY: If reranker is enabled use retrieve_reranked (async, uses LLM
                # to cross-score query+passage pairs). Otherwise fall back to the
                # synchronous BM25+TF-IDF retrieve() run in an executor thread.
                if reranker is not None:
                    results = await retriever.retrieve_reranked(cite, top_k=1, reranker=reranker)
                else:
                    # WHY run_in_executor: BM25 scoring and numpy ops are CPU-bound sync
                    # code. Off-loading to a thread keeps the event loop free for other
                    # concurrent Telegram requests.
                    results = await loop.run_in_executor(None, retriever.retrieve, cite, 1)
                para_ref = _find_paragraph_ref(cite, paragraphs)

                # WHY: retriever.py falls back to returning top_k even when no chunk
                # passes the similarity_threshold — so we must gate here, not there.
                # A score below threshold means the retriever found no genuine match;
                # marking such a citation verified=True would silently hallucinate.
                if results and results[0].score >= cfg.retriever_similarity_threshold:
                    best = results[0]
                    chunk_id = f"{best.child.source_doc}::{best.child.chunk_index}"
                    grounded.append({
                        "chunk_id": chunk_id,
                        "source": cite,
                        "paragraph_ref": para_ref,
                        "verified": True,
                        "score": best.score,
                    })
                    all_chunks.append({
                        "chunk_id": chunk_id,
                        "child_text": best.child.chunk_text,
                        "parent_text": best.parent.chunk_text,
                        "source_doc": best.child.source_doc,
                        "section_id": best.child.section_id,
                        "bm25_score": best.bm25_score,
                        "vector_score": best.vector_score,
                    })
                else:
                    grounded.append({
                        "chunk_id": None,
                        "source": cite,
                        "paragraph_ref": para_ref,
                        "verified": False,
                        "score": 0.0,
                    })
                    unverified.append(cite)

            verified_count = sum(1 for g in grounded if g["verified"])
            console.print(
                f"[green]✓ {verified_count} grounded[/green]  "
                f"[yellow]⚠ {len(unverified)} unverified[/yellow]"
            )

            return {
                "citations_verified": len(unverified) == 0,
                "unverified_citations": unverified if unverified else None,
                "grounded_citations": grounded,
                "retrieval_chunks": all_chunks,
            }

        # ----------------------------------------------------------------
        # Phase 4 fallback: no findings → corpus substring check
        # ----------------------------------------------------------------
        verified, unverified = _verify_citations(raw, findings)
        console.print(
            f"[green]✓ {len(verified)} verified[/green]  "
            f"[yellow]⚠ {len(unverified)} unverified[/yellow]"
        )
        # Build minimal grounded_citations so review node can always read the field
        grounded_fallback = [
            {
                "chunk_id": None,
                "source": c,
                "paragraph_ref": _find_paragraph_ref(c, paragraphs),
                "verified": c in verified,
                "score": 1.0 if c in verified else 0.0,
            }
            for c in raw
        ]
        return {
            "citations_verified": len(unverified) == 0,
            "unverified_citations": unverified if unverified else None,
            "grounded_citations": grounded_fallback,
            "retrieval_chunks": [],
        }

    except Exception as e:
        return {"error": str(e)}
