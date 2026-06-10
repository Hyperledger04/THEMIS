"""Tests for the dynamic skill router — manifest, LLM router call, string-match."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from lexagent.skills.loader import (
    _parse_frontmatter,
    _string_match_skill_name,
    build_skills_manifest,
    route_skills,
)


# ── _parse_frontmatter extracts description ──────────────────────────────────

def test_parse_frontmatter_extracts_description():
    content = (
        "---\n"
        "name: test_skill\n"
        "description: A test skill for unit testing.\n"
        "trigger_keywords: [test, demo]\n"
        "matter_types: [test]\n"
        "---\n\n# Body\n"
    )
    parsed = _parse_frontmatter(content)
    assert parsed["description"] == "A test skill for unit testing."


def test_parse_frontmatter_description_defaults_to_empty():
    content = (
        "---\n"
        "name: no_desc\n"
        "trigger_keywords: [x]\n"
        "matter_types: [x]\n"
        "---\n\n# Body\n"
    )
    parsed = _parse_frontmatter(content)
    assert parsed["description"] == ""


# ── build_skills_manifest ─────────────────────────────────────────────────────

def test_build_skills_manifest_returns_name_description_dict(tmp_path):
    skill_a = tmp_path / "skill_a.md"
    skill_a.write_text(
        "---\nname: skill_a\ndescription: Desc A.\ntrigger_keywords: [a]\nmatter_types: [a]\n---\n\n# Body A\n"
    )
    skill_b = tmp_path / "skill_b.md"
    skill_b.write_text(
        "---\nname: skill_b\ndescription: Desc B.\ntrigger_keywords: [b]\nmatter_types: [b]\n---\n\n# Body B\n"
    )
    empty_user = tmp_path / "user_skills"
    empty_user.mkdir()

    manifest = build_skills_manifest(tmp_path, empty_user)
    assert manifest == {"skill_a": "Desc A.", "skill_b": "Desc B."}


def test_build_skills_manifest_user_overrides_bundled(tmp_path):
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    user = tmp_path / "user"
    user.mkdir()

    (bundled / "s138.md").write_text(
        "---\nname: s138\ndescription: Bundled desc.\ntrigger_keywords: [x]\nmatter_types: [x]\n---\n"
    )
    (user / "s138.md").write_text(
        "---\nname: s138\ndescription: User override desc.\ntrigger_keywords: [x]\nmatter_types: [x]\n---\n"
    )
    manifest = build_skills_manifest(bundled, user)
    assert manifest["s138"] == "User override desc."


# ── _string_match_skill_name ──────────────────────────────────────────────────

def test_string_match_returns_name_for_s138(tmp_path):
    skill_file = tmp_path / "s138_complaint.md"
    skill_file.write_text(
        "---\nname: s138_complaint\ndescription: S138.\ntrigger_keywords: [cheque, 138, ni act]\nmatter_types: [s138_complaint]\n---\n"
    )
    empty = tmp_path / "user"
    empty.mkdir()

    result = _string_match_skill_name("cheque dishonour case", tmp_path, empty)
    assert result == "s138_complaint"


def test_string_match_returns_none_when_no_match(tmp_path):
    empty = tmp_path / "user"
    empty.mkdir()
    result = _string_match_skill_name("arbitration petition", tmp_path, empty)
    assert result is None


# ── route_skills ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_route_skills_returns_selected_from_llm():
    manifest = {
        "s138_complaint": "S.138 cheque dishonour.",
        "bail_application": "Bail application.",
    }
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"selected": ["s138_complaint"], "unmatched": []}'
                )
            )
        ]
    )
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await route_skills("S.138 cheque case", manifest, cfg)
    assert result["selected"] == ["s138_complaint"]
    assert result["unmatched"] == []


@pytest.mark.asyncio
async def test_route_skills_filters_nonexistent_skills():
    manifest = {"s138_complaint": "S.138 cheque."}
    mock_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content='{"selected": ["s138_complaint", "arbitration_petition"], "unmatched": ["arbitration_petition"]}'
                )
            )
        ]
    )
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await route_skills("arbitration matter", manifest, cfg)
    assert "arbitration_petition" not in result["selected"]


@pytest.mark.asyncio
async def test_route_skills_returns_empty_on_exception():
    manifest = {"s138_complaint": "S.138 cheque."}
    cfg = SimpleNamespace(skill_router_model="openai/gpt-4.1-mini", openai_api_key="test")
    with patch("lexagent.skills.loader.litellm.acompletion", side_effect=Exception("API error")):
        result = await route_skills("any matter", manifest, cfg)
    assert result == {"selected": [], "unmatched": []}
