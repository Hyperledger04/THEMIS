"""Tests for the contract_review node."""

import pytest

from themis.nodes.contract_review import (
    _build_risk_analysis,
    _chunk_contract,
    run,
)


# ---------------------------------------------------------------------------
# _chunk_contract
# ---------------------------------------------------------------------------

def test_short_contract_not_chunked():
    text = "This is a short contract."
    chunks = _chunk_contract(text, max_chars=1000)
    assert chunks == [text]


def test_long_contract_split_into_chunks():
    # Create a contract with multiple paragraphs that exceeds the limit
    paragraph = "A" * 200 + "\n\n"
    long_contract = paragraph * 10  # ~2000 chars
    chunks = _chunk_contract(long_contract, max_chars=500)
    assert len(chunks) > 1
    # All original content should be represented
    total_chars = sum(len(c) for c in chunks)
    assert total_chars > 0


def test_empty_contract_returns_single_empty_chunk():
    chunks = _chunk_contract("", max_chars=100)
    assert chunks == [""]


# ---------------------------------------------------------------------------
# _build_risk_analysis
# ---------------------------------------------------------------------------

_SAMPLE_REPORT = """
### Contract Risk Report

**Overall Risk Level**: HIGH
**Contract Type**: Software Services Agreement
**Jurisdiction**: India

---

### Key Findings

**HIGH — Liability**
*Clause/Section*: Clause 8.2
*Issue*: No cap on liability for consequential damages
*Impact*: Vendor exposed to unlimited consequential loss claims
*Recommendation*: Insert limitation of liability clause capping at 12 months of fees

**MEDIUM — Termination**
*Clause/Section*: Clause 12
*Issue*: Termination for convenience requires only 7 days notice
*Impact*: Insufficient wind-down time for vendor
*Recommendation*: Negotiate to 30 days minimum notice
"""


def test_build_risk_analysis_overall_risk():
    result = _build_risk_analysis(_SAMPLE_REPORT)
    assert result["overall_risk"] == "HIGH"


def test_build_risk_analysis_contract_type():
    result = _build_risk_analysis(_SAMPLE_REPORT)
    assert "Software" in result["contract_type"]


def test_build_risk_analysis_finding_counts():
    result = _build_risk_analysis(_SAMPLE_REPORT)
    assert result["high_count"] == 1
    assert result["medium_count"] == 1
    assert result["low_count"] == 0
    assert result["finding_count"] == 2


def test_build_risk_analysis_unknown_for_empty_report():
    result = _build_risk_analysis("No structured content here.")
    assert result["overall_risk"] == "UNKNOWN"
    assert result["finding_count"] == 0


# ---------------------------------------------------------------------------
# run() node
# ---------------------------------------------------------------------------

def _contract_state(pdf_path: str | None = "/tmp/test.pdf") -> dict:
    return {
        "user_input": "Review this contract",
        "matter_id": "M-CTEST",
        "workflow_mode": "contract_review",
        "contract_upload_path": pdf_path,
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],
    }


@pytest.mark.asyncio
async def test_run_returns_error_when_no_upload_path():
    state = _contract_state(pdf_path=None)
    result = await run(state)
    assert "error" in result
    assert "contract_upload_path" in result["error"]


@pytest.mark.asyncio
async def test_run_returns_error_when_file_not_found():
    state = _contract_state(pdf_path="/nonexistent/path/contract.pdf")
    result = await run(state)
    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_run_returns_error_when_pdf_extraction_fails(tmp_path, monkeypatch):
    """If pdfplumber returns empty text, node should return an error."""
    # Create a dummy file so existence check passes
    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        "themis.nodes.contract_review._extract_pdf_text",
        lambda path: "",  # simulate extraction failure
    )

    state = _contract_state(pdf_path=str(fake_pdf))
    result = await run(state)
    assert "error" in result
    assert "could not extract" in result["error"]


@pytest.mark.asyncio
async def test_run_produces_draft_output_on_success(tmp_path, monkeypatch):
    """Happy path: PDF extracted, LLM returns risk report."""
    fake_pdf = tmp_path / "contract.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    # Patch PDF extraction
    monkeypatch.setattr(
        "themis.nodes.contract_review._extract_pdf_text",
        lambda path: "This is a sample contract between Party A and Party B.",
    )

    # Patch LLM call
    class _FakeChoice:
        class message:
            content = _SAMPLE_REPORT

    class _FakeResponse:
        choices = [_FakeChoice()]

    async def _fake_completion(**kwargs):
        return _FakeResponse()

    monkeypatch.setattr("litellm.acompletion", _fake_completion)

    state = _contract_state(pdf_path=str(fake_pdf))
    result = await run(state)

    assert "error" not in result
    assert result.get("draft_output")
    assert result.get("contract_review_output")
    assert result.get("contract_risk_analysis")
    assert result["contract_risk_analysis"]["overall_risk"] == "HIGH"
    assert result.get("plain_english_summary")
    assert "messages" in result


@pytest.mark.asyncio
async def test_run_workflow_mode_contract_review_in_graph(monkeypatch):
    """Verify graph routes to contract_review node when workflow_mode is set."""
    from themis.graph import build_graph

    # Mock intake.run — intake is the graph entry point and always runs first.
    # We return intake_complete=True immediately to bypass the LLM call.
    async def _mock_intake_run(state):
        return {"intake_complete": True, "workflow_mode": state.get("workflow_mode", "draft")}

    monkeypatch.setattr("themis.nodes.intake.run", _mock_intake_run)

    # Patch contract_review.run to avoid actual PDF/LLM calls
    async def _mock_contract_run(state):
        return {
            "draft_output": "Mock risk report",
            "contract_review_output": "Mock risk report",
            "contract_risk_analysis": {
                "overall_risk": "LOW", "findings": [], "finding_count": 0,
                "high_count": 0, "medium_count": 0, "low_count": 0,
                "contract_type": "Test",
            },
            "plain_english_summary": "All clear.",
            "messages": [],
        }

    monkeypatch.setattr("themis.nodes.contract_review.run", _mock_contract_run)

    graph = build_graph().compile()
    initial_state = {
        "user_input": "Review this contract",
        "matter_id": "M-GR01",
        "intake_complete": False,
        "workflow_mode": "contract_review",
        "contract_upload_path": "/tmp/fake.pdf",
        "citations_verified": False,
        "messages": [],
    }

    final_state = await graph.ainvoke(initial_state)
    assert final_state.get("draft_output") == "Mock risk report"
    assert final_state.get("contract_risk_analysis", {}).get("overall_risk") == "LOW"
