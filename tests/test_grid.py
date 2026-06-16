import pytest
from unittest.mock import AsyncMock, patch
from themis.nodes.grid import run

BASE_STATE = {
    "matter_id": "test-matter-001",
    "grid_questions": ["What is the notice period?", "Who are the parties?"],
    "messages": [],
    "error": None,
}

@pytest.mark.asyncio
async def test_grid_returns_results_dict():
    mock_qa = AsyncMock(return_value={"qa_answer": "30 days", "qa_citations": []})
    fake_docs = ["contract_A.pdf", "contract_B.pdf"]
    with patch("themis.nodes.grid._list_matter_docs", return_value=fake_docs), \
         patch("themis.nodes.grid._run_qa", mock_qa):
        result = await run(BASE_STATE)
    assert "grid_results" in result
    assert "What is the notice period?" in result["grid_results"]
    assert "contract_A.pdf" in result["grid_results"]["What is the notice period?"]

@pytest.mark.asyncio
async def test_grid_empty_questions_returns_empty():
    result = await run({**BASE_STATE, "grid_questions": []})
    assert result == {}

@pytest.mark.asyncio
async def test_grid_captures_qa_error():
    mock_qa = AsyncMock(side_effect=RuntimeError("retrieval failed"))
    with patch("themis.nodes.grid._list_matter_docs", return_value=["a.pdf"]), \
         patch("themis.nodes.grid._run_qa", mock_qa):
        result = await run(BASE_STATE)
    assert "grid_results" in result
    err_val = list(result["grid_results"]["What is the notice period?"].values())[0]
    assert "error" in err_val.lower()


# CLI test
from typer.testing import CliRunner
from themis.cli import app

runner = CliRunner()

def test_grid_cli_help_mentions_questions():
    result = runner.invoke(app, ["grid", "--help"])
    assert result.exit_code == 0
    assert "questions" in result.output.lower()
