"""Tests for the research node — runs with stub backend (no browser required)."""

import os
import pytest

os.environ.setdefault("LEX_KANOON_BACKEND", "stub")

from lexagent.nodes.research import _build_search_query, _extract_statutes, run


def _state(**overrides):
    base = {
        "user_input": "landlord refused to return security deposit",
        "matter_id": "M-001",
        "matter_type": "civil suit",
        "parties": {"plaintiff": "Tenant A", "defendant": "Landlord B"},
        "jurisdiction": "Delhi High Court",
        "jurisdiction_country": "IN",
        "purpose": "money recovery suit for security deposit",
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],
    }
    base.update(overrides)
    return base


def test_build_query_includes_matter_type():
    q = _build_search_query(_state())
    assert "civil suit" in q


def test_build_query_includes_jurisdiction():
    q = _build_search_query(_state())
    assert "Delhi High Court" in q


def test_build_query_falls_back_to_user_input_when_no_fields():
    q = _build_search_query({"user_input": "my matter brief", "messages": []})
    assert "my matter brief" in q


def test_extract_statutes_from_text():
    results = [
        {
            "full_text": "Under CPC Order XXXIX Rule 1&2 and Specific Relief Act Section 38",
            "snippet": "",
        }
    ]
    statutes = _extract_statutes(results)
    assert any("CPC" in s for s in statutes)


def test_extract_statutes_returns_list():
    assert isinstance(_extract_statutes([]), list)


@pytest.mark.asyncio
async def test_run_returns_research_findings():
    result = await run(_state())
    assert "research_findings" in result
    assert isinstance(result["research_findings"], list)


@pytest.mark.asyncio
async def test_run_returns_limitation_analysis():
    result = await run(_state())
    assert "limitation_analysis" in result
    assert isinstance(result["limitation_analysis"], str)
    assert len(result["limitation_analysis"]) > 0


@pytest.mark.asyncio
async def test_run_returns_statutes_cited():
    result = await run(_state())
    assert "statutes_cited" in result
    assert isinstance(result["statutes_cited"], list)


@pytest.mark.asyncio
async def test_run_does_not_raise_on_missing_optional_fields():
    minimal = {
        "user_input": "eviction matter",
        "intake_complete": True,
        "citations_verified": False,
        "messages": [],
    }
    result = await run(minimal)
    assert "error" not in result


@pytest.mark.asyncio
async def test_run_catches_exceptions_into_error_key(monkeypatch):
    async def bad_kanoon(*a, **kw):
        raise RuntimeError("network failure")

    # Patch both the kanoon function and the config so the node tries to call it
    class _FakeConfig:
        kanoon_backend = "playwright"
        kanoon_max_results = 1
        kanoon_headless = True

    monkeypatch.setattr("lexagent.nodes.research.search_and_fetch", bad_kanoon)
    monkeypatch.setattr("lexagent.nodes.research.LexConfig", _FakeConfig)
    result = await run(_state())
    assert "error" in result
