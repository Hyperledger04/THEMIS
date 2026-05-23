"""Tests for lexagent/nodes/review.py"""
import pytest
from lexagent.nodes.review import run, _word_count, _jurisdiction_limit


# -----------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------

def test_word_count_empty():
    assert _word_count("") == 0


def test_word_count_sentence():
    assert _word_count("this is four words") == 4


def test_jurisdiction_limit_known_type():
    assert _jurisdiction_limit("injunction") == 5000


def test_jurisdiction_limit_substring_match():
    assert _jurisdiction_limit("application for injunction") == 5000


def test_jurisdiction_limit_unknown_returns_default():
    assert _jurisdiction_limit("unknown doc type") == 12000


def test_jurisdiction_limit_none_returns_default():
    assert _jurisdiction_limit(None) == 12000


# -----------------------------------------------------------------------
# run (async)
# -----------------------------------------------------------------------

def _base_state(**overrides) -> dict:
    base = {
        "draft_output": "This is a valid draft with sufficient content.",
        "unverified_citations": None,
        "grounded_citations": [],
        "matter_type": "legal notice",
        "parties": {"plaintiff": "A", "defendant": "B"},
        "jurisdiction": "Delhi High Court",
        "matter_id": "M-TEST-001",
        "docx_path": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_review_passes_clean_state():
    result = await run(_base_state())
    assert result.get("error") is None
    assert result.get("risk_annotations") is None


@pytest.mark.asyncio
async def test_review_flags_unverified_citations():
    state = _base_state(unverified_citations=["AIR 1978 SC 597"])
    result = await run(state)
    annotations = result.get("risk_annotations") or []
    assert len(annotations) > 0
    assert any("citation" in a["note"].lower() for a in annotations)


@pytest.mark.asyncio
async def test_review_flags_empty_draft():
    state = _base_state(draft_output="")
    result = await run(state)
    annotations = result.get("risk_annotations") or []
    assert any("empty" in a["note"].lower() for a in annotations)


@pytest.mark.asyncio
async def test_review_flags_overlong_draft():
    long_draft = " ".join(["word"] * 3000)
    state = _base_state(draft_output=long_draft, matter_type="legal notice")
    result = await run(state)
    annotations = result.get("risk_annotations") or []
    assert any("word" in a["note"].lower() or "exceed" in a["note"].lower() for a in annotations)


@pytest.mark.asyncio
async def test_review_no_docx_when_path_is_none():
    result = await run(_base_state(docx_path=None))
    assert result.get("docx_path") is None


@pytest.mark.asyncio
async def test_review_writes_docx_when_path_given(tmp_path):
    out = str(tmp_path / "draft.docx")
    state = _base_state(docx_path=out)
    result = await run(state)
    assert result.get("docx_path") == out
    import os
    assert os.path.exists(out)


@pytest.mark.asyncio
async def test_review_error_caught_not_raised():
    # Pass an invalid state type to trigger an internal error path
    result = await run(None)  # type: ignore[arg-type]
    assert "error" in result


@pytest.mark.asyncio
async def test_review_multiple_unverified_citations():
    cites = [f"AIR 200{i} SC {i}00" for i in range(5)]
    state = _base_state(unverified_citations=cites)
    result = await run(state)
    annotations = result.get("risk_annotations") or []
    assert len(annotations) >= 1
