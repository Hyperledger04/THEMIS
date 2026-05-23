"""Tests for lexagent/tools/raptor_summarizer.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from lexagent.tools.chunker import Chunk
from lexagent.tools.raptor_summarizer import (
    RaptorNode,
    RaptorSummarizer,
    raptor_tree_to_findings,
)


def _make_llm(summary_text: str = "Doctrinal summary.") -> MagicMock:
    """Return a mock LLM whose ainvoke() returns a fixed summary."""
    llm = MagicMock()
    response = MagicMock()
    response.content = summary_text
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            source_doc="test.txt",
            section_id=f"Section {i}",
            chunk_index=i,
            chunk_text=f"This is content for section {i} about property disputes and injunctions.",
        )
        for i in range(n)
    ]


# -----------------------------------------------------------------------
# build_tree — empty input
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_tree_empty():
    summarizer = RaptorSummarizer(llm=_make_llm(), max_layers=2)
    tree = await summarizer.build_tree([])
    assert tree == []


# -----------------------------------------------------------------------
# build_tree — single chunk (no clustering needed)
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_tree_single_chunk():
    summarizer = RaptorSummarizer(llm=_make_llm(), max_layers=2)
    chunks = _make_chunks(1)
    tree = await summarizer.build_tree(chunks)
    # At least the leaf node should be present
    assert len(tree) >= 1
    assert tree[0].layer == 0


# -----------------------------------------------------------------------
# build_tree — multiple chunks, produces summary nodes
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_tree_produces_summary():
    summarizer = RaptorSummarizer(llm=_make_llm("Summary of cluster."), max_layers=1, max_cluster_size=2)
    chunks = _make_chunks(6)
    tree = await summarizer.build_tree(chunks)
    # Should have both layer-0 leaves and at least one layer-1 summary
    layers = {n.layer for n in tree}
    assert 0 in layers
    assert 1 in layers


@pytest.mark.asyncio
async def test_build_tree_summary_text_from_llm():
    expected = "Key legal principle from these cases."
    summarizer = RaptorSummarizer(llm=_make_llm(expected), max_layers=1, max_cluster_size=3)
    chunks = _make_chunks(4)
    tree = await summarizer.build_tree(chunks)
    summaries = [n.text for n in tree if n.layer == 1]
    assert any(expected in s for s in summaries)


# -----------------------------------------------------------------------
# build_tree — LLM failure falls back gracefully
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_tree_llm_failure_graceful():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("API down"))
    summarizer = RaptorSummarizer(llm=llm, max_layers=1, max_cluster_size=2)
    chunks = _make_chunks(4)
    # Should not raise; falls back to truncated first-node text
    tree = await summarizer.build_tree(chunks)
    assert isinstance(tree, list)


# -----------------------------------------------------------------------
# build_tree_from_findings
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_tree_from_findings():
    findings = [
        {"citation": "AIR 1978 SC 597", "full_text": "Property dispute judgment content. " * 20},
        {"case_name": "State v Raj", "snippet": "Injunction granted on property grounds. " * 10},
    ]
    summarizer = RaptorSummarizer(llm=_make_llm("Property law doctrine."), max_layers=1, max_cluster_size=5)
    tree = await summarizer.build_tree_from_findings(findings)
    assert isinstance(tree, list)


@pytest.mark.asyncio
async def test_build_tree_from_findings_empty():
    summarizer = RaptorSummarizer(llm=_make_llm(), max_layers=1)
    tree = await summarizer.build_tree_from_findings([])
    assert tree == []


# -----------------------------------------------------------------------
# raptor_tree_to_findings
# -----------------------------------------------------------------------

def test_raptor_tree_to_findings_filters_layer0():
    tree = [
        RaptorNode(layer=0, text="Original chunk.", source_chunks=["doc::0"]),
        RaptorNode(layer=1, text="Summary text.", source_chunks=["doc::0"]),
    ]
    findings = raptor_tree_to_findings(tree)
    # Only layer >= 1 nodes should appear
    assert len(findings) == 1
    assert findings[0]["source"] == "raptor_summary"
    assert "Summary text" in findings[0]["full_text"]


def test_raptor_tree_to_findings_empty_tree():
    assert raptor_tree_to_findings([]) == []


def test_raptor_tree_to_findings_structure():
    tree = [RaptorNode(layer=2, text="Deep summary.", source_chunks=["a::0", "b::1"])]
    findings = raptor_tree_to_findings(tree)
    assert findings[0]["case_name"] == "RAPTOR Summary (layer 2)"
    assert findings[0]["source_chunks"] == ["a::0", "b::1"]
