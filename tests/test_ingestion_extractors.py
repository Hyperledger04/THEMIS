"""Tests for lexagent/ingestion/extractors.py — LLM extraction pipeline."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from lexagent.ingestion.documents import PageText
from lexagent.ingestion.extractors import (
    ExtractionResult,
    _build_excerpt_index,
    _coerce_deadline_type,
    _coerce_role,
    _deduplicate_parties,
    _match_anchors,
    _parse_json,
    extract_from_pages,
    persist_extraction,
)
from lexagent.workspace.models import Party, SourceAnchor


# ---------------------------------------------------------------------------
# Pure helpers — no LLM needed
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_parses_clean_json(self):
        raw = json.dumps({"parties": [], "facts": [], "dates": [], "issues": [], "deadlines": []})
        result = _parse_json(raw)
        assert result["parties"] == []

    def test_strips_markdown_fence(self):
        raw = "```json\n{\"parties\": []}\n```"
        result = _parse_json(raw)
        assert result == {"parties": []}

    def test_extracts_embedded_json(self):
        raw = "Here is the extraction:\n{\"parties\": [{\"name\": \"X\"}]}\nEnd."
        result = _parse_json(raw)
        assert result["parties"][0]["name"] == "X"

    def test_returns_empty_dict_on_invalid(self):
        result = _parse_json("not json at all")
        assert result == {}


class TestCoerce:
    def test_valid_role_passes(self):
        assert _coerce_role("complainant") == "complainant"

    def test_invalid_role_becomes_other(self):
        assert _coerce_role("plaintiff") == "other"

    def test_valid_deadline_type(self):
        assert _coerce_deadline_type("limitation") == "limitation"

    def test_invalid_deadline_type_becomes_other(self):
        assert _coerce_deadline_type("court_date") == "other"


class TestDeduplicateParties:
    def test_removes_same_name_same_matter(self):
        parties = [
            Party(matter_id="M-001", name="Ramesh Kumar", role="complainant"),
            Party(matter_id="M-001", name="RAMESH KUMAR", role="complainant"),
        ]
        result = _deduplicate_parties(parties)
        assert len(result) == 1

    def test_keeps_different_names(self):
        parties = [
            Party(matter_id="M-001", name="Ramesh", role="complainant"),
            Party(matter_id="M-001", name="Suresh", role="respondent"),
        ]
        assert len(_deduplicate_parties(parties)) == 2


class TestAnchorMatching:
    def test_matches_substring(self):
        index = {"cheque was dishonoured": "anchor_1", "bank returned it": "anchor_2"}
        result = _match_anchors("The cheque was dishonoured on 14 March", index)
        assert "anchor_1" in result

    def test_returns_empty_on_no_match(self):
        index = {"some other text": "anchor_x"}
        result = _match_anchors("completely different excerpt", index)
        assert result == []


# ---------------------------------------------------------------------------
# extract_from_pages — mocked LLM
# ---------------------------------------------------------------------------

_VALID_EXTRACTION = {
    "parties": [
        {"name": "Ramesh Kumar", "role": "complainant"},
        {"name": "Suresh Sharma", "role": "respondent"},
    ],
    "facts": [
        {
            "text": "The cheque bearing no. 123456 was dishonoured.",
            "confidence": 0.95,
            "excerpt": "cheque bearing no. 123456 was dishonoured",
        }
    ],
    "dates": [
        {
            "date_text": "14 March 2026",
            "event": "Cheque dishonoured",
            "normalized_date": "2026-03-14",
            "confidence": 0.9,
            "excerpt": "dishonoured on 14 March 2026",
        }
    ],
    "issues": [
        {"text": "Whether the accused is liable under Section 138 NI Act", "category": "liability"}
    ],
    "deadlines": [
        {"title": "Notice period expiry", "due_date": "2026-04-14", "deadline_type": "notice"}
    ],
}


@pytest.mark.asyncio
async def test_extract_from_pages_returns_structured_result():
    pages = [PageText(page=1, text="The cheque bearing no. 123456 was dishonoured on 14 March 2026.", char_count=60)]
    anchors = [
        SourceAnchor(
            anchor_id="F1",
            matter_id="M-001",
            document_id="doc_001",
            page=1,
            line_start=1,
            excerpt="cheque bearing no. 123456 was dishonoured",
        )
    ]

    async def fake_llm(system, user):
        return json.dumps(_VALID_EXTRACTION)

    result = await extract_from_pages(
        matter_id="M-001",
        document_id="doc_001",
        pages=pages,
        anchors=anchors,
        llm_callable=fake_llm,
        run_id="run_001",
    )

    assert isinstance(result, ExtractionResult)
    assert len(result.parties) == 2
    assert len(result.facts) == 1
    assert result.facts[0].text == "The cheque bearing no. 123456 was dishonoured."
    assert len(result.chronology_items) == 1
    assert result.chronology_items[0].normalized_date == "2026-03-14"
    assert len(result.issues) == 1
    assert len(result.deadlines) == 1
    assert result.deadlines[0].due_date == "2026-04-14"


@pytest.mark.asyncio
async def test_extract_from_pages_skips_blank_pages():
    pages = [
        PageText(page=1, text="   \n\n  ", char_count=6),  # blank
        PageText(page=2, text="Valid content here.", char_count=19),
    ]

    call_count = 0

    async def counting_llm(system, user):
        nonlocal call_count
        call_count += 1
        return json.dumps({"parties": [], "facts": [], "dates": [], "issues": [], "deadlines": []})

    await extract_from_pages("M-001", "doc_001", pages, [], counting_llm)
    assert call_count == 1  # Only page 2 should trigger an LLM call


@pytest.mark.asyncio
async def test_extract_from_pages_handles_llm_error_gracefully():
    pages = [PageText(page=1, text="Some content", char_count=12)]

    async def failing_llm(system, user):
        raise ValueError("LLM timeout")

    result = await extract_from_pages("M-001", "doc_001", pages, [], failing_llm)
    # Should return empty result rather than raising
    assert result.facts == []
    assert result.parties == []


@pytest.mark.asyncio
async def test_persist_extraction_calls_repo_methods():
    pages = [PageText(page=1, text="Complaint filed on 1 Jan 2026.", char_count=30)]

    async def fake_llm(system, user):
        return json.dumps(_VALID_EXTRACTION)

    result = await extract_from_pages("M-001", "doc_001", pages, [], fake_llm)

    repo = MagicMock()
    persist_extraction(result, repo)

    repo.bulk_create_facts.assert_called_once()
    repo.bulk_create_chronology.assert_called_once()
    # Parties and issues call individual create methods
    assert repo.create_party.call_count == 2
