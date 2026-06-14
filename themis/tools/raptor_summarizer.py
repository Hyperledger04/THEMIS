# RAPTOR hierarchical summarizer for legal research findings.
#
# Inspired by RAGFlow's rag/raptor.py (RecursiveAbstractiveProcessing4TreeOrganizedRetrieval).
# RAGFlow's RAPTOR clusters document chunks, summarizes each cluster via LLM,
# embeds the summaries, and recurses to build a multi-level tree.
#
# Our simplified variant:
#   - Uses TF-IDF cosine similarity (already in deps) instead of embedding models
#   - Uses sklearn AgglomerativeClustering instead of GMM (simpler, no scipy required)
#   - Produces up to max_layers of cluster summaries
#   - Injects layer-1 summaries back into research_findings as synthetic entries
#     so the draft node gets both fine-grained citations AND doctrinal overview

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import AgglomerativeClustering  # type: ignore[import]
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import]
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import]

from themis.tools.chunker import Chunk, chunk_text


@dataclass
class RaptorNode:
    layer: int                      # 0 = original chunk, 1+ = summary
    text: str                       # chunk text or summary text
    source_chunks: list[str]        # chunk_ids of leaves that produced this node
    children: list["RaptorNode"] = field(default_factory=list)


class RaptorSummarizer:
    """
    Build a hierarchical summary tree from a list of Chunks.

    Usage:
        summarizer = RaptorSummarizer(cfg=cfg, max_layers=2)
        tree = await summarizer.build_tree(chunks)
        # tree is a list of RaptorNode (layer 0 = leaves, layer 1+ = summaries)
    """

    def __init__(
        self,
        cfg,
        max_layers: int = 2,
        max_cluster_size: int = 5,
    ) -> None:
        self._cfg = cfg
        self._max_layers = max_layers
        self._max_cluster_size = max_cluster_size

    async def build_tree(self, chunks: list[Chunk]) -> list[RaptorNode]:
        """
        Build the RAPTOR tree from a flat list of chunks.
        Returns all nodes (leaves + summaries at each layer).
        """
        if not chunks:
            return []

        # Layer 0: wrap original chunks as RaptorNodes
        nodes: list[RaptorNode] = [
            RaptorNode(
                layer=0,
                text=c.chunk_text,
                source_chunks=[f"{c.source_doc}::{c.chunk_index}"],
            )
            for c in chunks
        ]
        all_nodes = list(nodes)

        for layer in range(1, self._max_layers + 1):
            if len(nodes) <= 1:
                # Nothing left to cluster
                break
            summary_nodes = await self._summarize_layer(nodes, layer)
            if not summary_nodes:
                break
            all_nodes.extend(summary_nodes)
            nodes = summary_nodes  # next layer clusters the summaries

        return all_nodes

    async def build_tree_from_findings(
        self, findings: list[dict], child_max_tokens: int = 256
    ) -> list[RaptorNode]:
        """Convenience: build tree directly from research_findings dicts."""
        chunks: list[Chunk] = []
        for finding in findings:
            source = finding.get("citation") or finding.get("case_name") or "unknown"
            body = (
                finding.get("full_text")
                or finding.get("header", "") + "\n" + finding.get("snippet", "")
            ).strip()
            if body:
                chunks.extend(chunk_text(body, source_doc=source, max_tokens=child_max_tokens))
        return await self.build_tree(chunks)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    async def _summarize_layer(
        self, nodes: list[RaptorNode], layer: int
    ) -> list[RaptorNode]:
        """
        Cluster nodes by TF-IDF cosine similarity, then summarize each cluster.
        Returns a list of summary RaptorNodes at the given layer.
        """
        texts = [n.text for n in nodes]
        clusters = self._cluster(texts)

        # Group nodes by cluster label
        groups: dict[int, list[RaptorNode]] = {}
        for node, label in zip(nodes, clusters):
            groups.setdefault(label, []).append(node)

        # Summarise each cluster concurrently
        tasks = [self._summarize_cluster(group, layer) for group in groups.values()]
        summary_nodes: list[RaptorNode] = await asyncio.gather(*tasks)
        return [n for n in summary_nodes if n.text.strip()]

    def _cluster(self, texts: list[str]) -> list[int]:
        """
        Cluster texts using TF-IDF + AgglomerativeClustering.
        Returns a list of integer cluster labels, one per text.
        """
        if len(texts) <= self._max_cluster_size:
            # All in one cluster
            return [0] * len(texts)

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            # Empty vocabulary (all texts are whitespace/stopwords)
            return [0] * len(texts)

        # WHY: distance_threshold instead of n_clusters — we don't know in
        # advance how many clusters are appropriate. 0.7 cosine distance
        # groups roughly similar legal paragraphs together.
        n_clusters = max(1, len(texts) // self._max_cluster_size)
        model = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric="cosine",
            linkage="average",
        )
        # Agglomerative needs a dense array
        dense = matrix.toarray()
        labels: list[int] = model.fit_predict(dense).tolist()
        return labels

    async def _summarize_cluster(
        self, nodes: list[RaptorNode], layer: int
    ) -> RaptorNode:
        """Generate an LLM summary for a cluster of nodes."""
        combined = "\n\n".join(n.text[:500] for n in nodes)  # cap to avoid token overflow
        source_ids: list[str] = []
        for n in nodes:
            source_ids.extend(n.source_chunks)

        prompt = (
            "You are a legal research assistant. The following passages are excerpts from "
            "Indian court judgments and legal documents. Write a concise 2-3 sentence "
            "doctrinal summary that captures the core legal principle or holding shared "
            "across these passages. Do not list individual case names — focus on the rule.\n\n"
            f"{combined}"
        )

        try:
            from themis.nodes._llm import call_llm
            result = await call_llm([{"role": "user", "content": prompt}], self._cfg)
            summary_text = result["content"]
        except Exception:
            # WHY: If the LLM call fails, fall back to the first node's text truncated.
            # Better than crashing the research pipeline mid-run.
            summary_text = nodes[0].text[:300] if nodes else ""

        return RaptorNode(
            layer=layer,
            text=summary_text.strip(),
            source_chunks=source_ids,
            children=nodes,
        )


def raptor_tree_to_findings(tree: list[RaptorNode]) -> list[dict]:
    """
    Convert layer-1+ RAPTOR summary nodes into research_findings-compatible dicts.
    These synthetic entries are injected alongside real Kanoon results so the
    draft node gets doctrinal summaries as well as individual citations.
    """
    summaries: list[dict] = []
    for node in tree:
        if node.layer >= 1:
            summaries.append({
                "case_name": f"RAPTOR Summary (layer {node.layer})",
                "citation": None,
                "snippet": node.text[:500],
                "full_text": node.text,
                "source": "raptor_summary",
                "source_chunks": node.source_chunks,
                "url": None,
                "status": "raptor",
            })
    return summaries
