"""Tests for the cite node — citation extraction and cross-reference verification."""

import pytest
from themis.nodes.cite import _extract_citations, _verify_citations, run


# ---------------------------------------------------------------------------
# _extract_citations
# ---------------------------------------------------------------------------

def test_extracts_air_citation():
    text = "As held in AIR 1978 SC 597, the principle is settled."
    citations = _extract_citations(text)
    assert "AIR 1978 SC 597" in citations


def test_extracts_scc_citation_with_volume():
    text = "See (2021) 3 SCC 415 for the ratio."
    citations = _extract_citations(text)
    assert any("SCC" in c for c in citations)


def test_returns_empty_for_no_citations():
    assert _extract_citations("There are no citations here.") == []


def test_deduplicates_repeated_citations():
    text = "AIR 1978 SC 597 was followed. See also AIR 1978 SC 597."
    citations = _extract_citations(text)
    assert citations.count("AIR 1978 SC 597") == 1


def test_extracts_multiple_different_citations():
    text = "AIR 1978 SC 597 and AIR 2005 Del 100 were both cited."
    citations = _extract_citations(text)
    assert len(citations) == 2


# ---------------------------------------------------------------------------
# _verify_citations
# ---------------------------------------------------------------------------

def test_verified_when_citation_in_findings():
    findings = [{"full_text": "AIR 1978 SC 597 is the leading case.", "header": "", "snippet": ""}]
    verified, unverified = _verify_citations(["AIR 1978 SC 597"], findings)
    assert "AIR 1978 SC 597" in verified
    assert unverified == []


def test_unverified_when_citation_absent_from_findings():
    findings = [{"full_text": "unrelated judgment text", "header": "", "snippet": ""}]
    verified, unverified = _verify_citations(["AIR 1978 SC 597"], findings)
    assert "AIR 1978 SC 597" in unverified
    assert verified == []


def test_empty_findings_puts_all_citations_in_unverified():
    _, unverified = _verify_citations(["AIR 1978 SC 597"], [])
    assert "AIR 1978 SC 597" in unverified


def test_empty_citations_returns_empty_lists():
    v, u = _verify_citations([], [{"full_text": "some text", "header": "", "snippet": ""}])
    assert v == []
    assert u == []


# ---------------------------------------------------------------------------
# run() node contract
# ---------------------------------------------------------------------------

def _state_with_draft(draft_text: str, findings: list | None = None):
    return {
        "user_input": "test",
        "matter_id": "M-001",
        "draft_output": draft_text,
        "research_findings": findings or [],
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],
    }


@pytest.mark.asyncio
async def test_run_sets_citations_verified_true_when_all_verified(monkeypatch):
    """Phase 5 path: mock a high-score retriever so the citation is grounded."""

    class _HighScoreRetriever:
        def retrieve(self, query, top_k=1):
            return [_FakeResult(0.9)]  # well above 0.35 threshold

        @classmethod
        def from_findings(cls, findings, **kwargs):
            return cls()

    monkeypatch.setattr("themis.tools.retriever.HybridRetriever", _HighScoreRetriever)
    findings = [{"full_text": "AIR 1978 SC 597", "header": "", "snippet": ""}]
    state = _state_with_draft("As per AIR 1978 SC 597, the law is clear.", findings)
    result = await run(state)
    assert result["citations_verified"] is True


@pytest.mark.asyncio
async def test_run_sets_citations_verified_false_when_unverified_remain():
    state = _state_with_draft("As per AIR 1978 SC 597, the law is clear.", findings=[])
    result = await run(state)
    assert result["citations_verified"] is False
    assert "AIR 1978 SC 597" in result["unverified_citations"]


@pytest.mark.asyncio
async def test_run_unverified_citations_is_none_when_all_verified(monkeypatch):
    """Phase 5 path: mock a high-score retriever so all citations are grounded."""

    class _HighScoreRetriever:
        def retrieve(self, query, top_k=1):
            return [_FakeResult(0.9)]

        @classmethod
        def from_findings(cls, findings, **kwargs):
            return cls()

    monkeypatch.setattr("themis.tools.retriever.HybridRetriever", _HighScoreRetriever)
    findings = [{"full_text": "AIR 1978 SC 597", "header": "", "snippet": ""}]
    state = _state_with_draft("See AIR 1978 SC 597.", findings)
    result = await run(state)
    assert result.get("unverified_citations") is None


@pytest.mark.asyncio
async def test_run_no_citations_in_draft_means_verified():
    state = _state_with_draft("The plaintiff submits the following arguments.")
    result = await run(state)
    assert result["citations_verified"] is True


@pytest.mark.asyncio
async def test_run_handles_missing_draft_gracefully():
    state = {
        "user_input": "test",
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],
    }
    result = await run(state)
    assert "error" not in result
    assert result["citations_verified"] is True


# ---------------------------------------------------------------------------
# CRIT-01: Threshold gate — low-score retriever result must not mark verified
# ---------------------------------------------------------------------------

class _FakeChild:
    source_doc = "test.txt"
    chunk_index = 0
    chunk_text = "some text"
    section_id = "s1"


class _FakeParent:
    chunk_text = "parent text"


class _FakeResult:
    """Simulates a RetrievalResult with a configurable score."""
    def __init__(self, score: float):
        self.score = score
        self.child = _FakeChild()
        self.parent = _FakeParent()
        self.bm25_score = score
        self.vector_score = score


class _FakeRetriever:
    def __init__(self, score: float):
        self._score = score

    def retrieve(self, query: str, top_k: int = 1) -> list:
        return [_FakeResult(self._score)]

    @classmethod
    def from_findings(cls, findings, **kwargs):
        return cls(0.1)  # below default threshold of 0.35


@pytest.mark.asyncio
async def test_low_score_retrieval_does_not_mark_citation_verified(monkeypatch):
    """CRIT-01: A retriever result below similarity_threshold must NOT produce verified=True."""
    import themis.nodes.cite as cite_module

    # Patch HybridRetriever so it returns a below-threshold score
    monkeypatch.setattr(
        "themis.tools.retriever.HybridRetriever",
        _FakeRetriever,
    )

    findings = [{"full_text": "some legal text", "header": "", "snippet": ""}]
    state = _state_with_draft("As per AIR 1978 SC 597, the law is clear.", findings)
    result = await run(state)

    # Score 0.1 is below default threshold 0.35 — must be unverified
    assert result["citations_verified"] is False
    assert "AIR 1978 SC 597" in (result.get("unverified_citations") or [])


@pytest.mark.asyncio
async def test_above_threshold_score_marks_citation_verified(monkeypatch):
    """CRIT-01 positive case: score above threshold marks citation verified."""

    class _HighScoreRetriever(_FakeRetriever):
        @classmethod
        def from_findings(cls, findings, **kwargs):
            return cls(0.9)  # well above 0.35 threshold

    monkeypatch.setattr(
        "themis.tools.retriever.HybridRetriever",
        _HighScoreRetriever,
    )

    findings = [{"full_text": "AIR 1978 SC 597", "header": "", "snippet": ""}]
    state = _state_with_draft("As per AIR 1978 SC 597, the law is clear.", findings)
    result = await run(state)

    assert result["citations_verified"] is True
    assert result.get("unverified_citations") is None
