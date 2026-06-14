# Tests for caching helpers in draft.py — written before implementation (TDD).
# Run with: uv run pytest tests/test_caching.py -v

import pytest

from themis.nodes.draft import (
    build_system_prompt_blocks,
    inject_memory_into_user_turn,
)


SOUL = {
    "raw": "# Lawyer Identity\n**Name:** Arjun Mehta\n**Bar:** Delhi HC",
    "name": "Arjun Mehta",
}
SKILL = "# Civil Litigation Skill\n## Structure\n1. Prayer\n2. Verification"


# ---------------------------------------------------------------------------
# inject_memory_into_user_turn — works for ALL providers
# ---------------------------------------------------------------------------


def test_inject_memory_prepends_memory_block():
    result = inject_memory_into_user_turn("Draft an injunction", "Prior matter: ABC vs XYZ")
    assert "<memory-context>" in result
    assert "Prior matter: ABC vs XYZ" in result
    assert "Draft an injunction" in result


def test_inject_memory_memory_comes_before_user_input():
    result = inject_memory_into_user_turn("My question", "My memory")
    memory_pos = result.index("<memory-context>")
    question_pos = result.index("My question")
    assert memory_pos < question_pos


def test_inject_memory_closes_tag():
    result = inject_memory_into_user_turn("Q", "M")
    assert "</memory-context>" in result


def test_inject_memory_empty_memory_returns_input_unchanged():
    result = inject_memory_into_user_turn("Just a question", "")
    # When memory is empty, return the user input without wrapping
    assert result == "Just a question"


def test_inject_memory_none_memory_returns_input_unchanged():
    result = inject_memory_into_user_turn("Just a question", None)
    assert result == "Just a question"


# ---------------------------------------------------------------------------
# build_system_prompt_blocks — Anthropic caching path
# ---------------------------------------------------------------------------


def test_cached_prompt_is_list_when_caching_enabled():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=True)
    assert isinstance(result, list)


def test_cached_prompt_list_has_one_block():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=True)
    assert len(result) == 1


def test_cached_prompt_block_has_cache_control():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=True)
    block = result[0]
    assert "cache_control" in block
    assert block["cache_control"]["type"] == "ephemeral"


def test_cached_prompt_block_contains_soul_content():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=True)
    block = result[0]
    assert "Arjun Mehta" in block["text"]


def test_cached_prompt_block_contains_skill_content():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=True)
    block = result[0]
    assert "Civil Litigation Skill" in block["text"]


def test_prompt_is_string_when_caching_disabled():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=False)
    assert isinstance(result, str)


def test_prompt_string_contains_soul_content():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=False)
    assert "Arjun Mehta" in result


def test_prompt_string_contains_skill_content():
    result = build_system_prompt_blocks(SOUL, SKILL, use_cache_control=False)
    assert "Civil Litigation Skill" in result


def test_cached_prompt_no_skill_still_works():
    result = build_system_prompt_blocks(SOUL, skill_content=None, use_cache_control=True)
    assert isinstance(result, list)
    assert "Arjun Mehta" in result[0]["text"]


def test_cached_prompt_no_soul_still_works():
    result = build_system_prompt_blocks(soul=None, skill_content=SKILL, use_cache_control=True)
    assert isinstance(result, list)
    assert "Civil Litigation Skill" in result[0]["text"]
