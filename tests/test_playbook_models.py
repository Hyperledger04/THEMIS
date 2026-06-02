"""Tests for lexagent/contract/models.py — PlaybookSpec, PositionResult, PlaybookExecution."""
from __future__ import annotations

import pytest

from lexagent.contract.models import (
    PlaybookExecution,
    PlaybookPosition,
    PlaybookSpec,
    PositionResult,
)


# ---------------------------------------------------------------------------
# PlaybookPosition
# ---------------------------------------------------------------------------

def test_playbook_position_required_fields():
    pos = PlaybookPosition(clause="Governing law", our_position="Delhi courts")
    assert pos.clause == "Governing law"
    assert pos.our_position == "Delhi courts"
    assert pos.rationale is None
    assert pos.precedents == []


def test_playbook_position_full():
    pos = PlaybookPosition(
        clause="Limitation",
        our_position="3 years",
        rationale="Standard contract act",
        precedents=["AIR 2001 SC 101"],
    )
    assert pos.rationale == "Standard contract act"
    assert len(pos.precedents) == 1


# ---------------------------------------------------------------------------
# PlaybookSpec.from_dict()
# ---------------------------------------------------------------------------

def _nda_dict() -> dict:
    return {
        "id": "nda",
        "name": "NDA — Standard Positions",
        "contract_type": "nda",
        "positions": [
            {
                "clause": "Confidentiality period",
                "our_position": "3 years from disclosure date",
                "rationale": "Tying to disclosure is more accurate",
            },
            {
                "clause": "Governing law",
                "our_position": "Indian law, Delhi courts",
            },
        ],
        "notes": "Default to one-way NDA.",
        "created": "2024-01-01",
        "source": "bundled",
    }


def test_playbook_spec_from_dict():
    spec = PlaybookSpec.from_dict(_nda_dict())
    assert spec.id == "nda"
    assert spec.name == "NDA — Standard Positions"
    assert spec.contract_type == "nda"
    assert len(spec.positions) == 2
    assert spec.notes == "Default to one-way NDA."
    assert spec.source == "bundled"


def test_playbook_spec_positions_are_typed():
    spec = PlaybookSpec.from_dict(_nda_dict())
    assert isinstance(spec.positions[0], PlaybookPosition)
    assert spec.positions[0].clause == "Confidentiality period"


def test_playbook_spec_minimal_dict():
    spec = PlaybookSpec.from_dict({"id": "test", "name": "Test", "contract_type": "other"})
    assert spec.positions == []
    assert spec.notes is None


def test_playbook_spec_from_dict_already_typed_positions():
    """from_dict should accept a mix of dicts and PlaybookPosition objects."""
    data = {
        "id": "x",
        "name": "X",
        "contract_type": "x",
        "positions": [PlaybookPosition(clause="A", our_position="B")],
    }
    spec = PlaybookSpec.from_dict(data)
    assert spec.positions[0].clause == "A"


# ---------------------------------------------------------------------------
# PositionResult
# ---------------------------------------------------------------------------

def test_position_result_defaults():
    r = PositionResult(clause="Governing law", our_position="Delhi courts", detected=True)
    assert r.severity == "ok"
    assert r.deviation is None
    assert r.excerpt is None


def test_position_result_with_deviation():
    r = PositionResult(
        clause="Governing law",
        our_position="Delhi courts",
        detected=True,
        deviation="Contract says Mumbai courts",
        severity="major",
    )
    assert r.severity == "major"


# ---------------------------------------------------------------------------
# PlaybookExecution.summary()
# ---------------------------------------------------------------------------

def test_playbook_execution_summary_empty():
    ex = PlaybookExecution(playbook_id="nda", document_path="/tmp/test.pdf")
    s = ex.summary()
    assert s["positions_checked"] == 0
    assert s["deviations"] == 0


def test_playbook_execution_summary_with_results():
    ex = PlaybookExecution(
        playbook_id="nda",
        document_path="/tmp/test.pdf",
        overall_risk="HIGH",
        results=[
            PositionResult(clause="A", our_position="X", detected=True, deviation="differs", severity="major"),
            PositionResult(clause="B", our_position="Y", detected=True, severity="ok"),
            PositionResult(clause="C", our_position="Z", detected=True, deviation="bad", severity="critical"),
        ],
    )
    s = ex.summary()
    assert s["positions_checked"] == 3
    assert s["deviations"] == 2
    assert s["critical"] == 1
    assert s["major"] == 1
    assert s["overall_risk"] == "HIGH"


def test_playbook_execution_default_status():
    ex = PlaybookExecution(playbook_id="nda", document_path="/tmp/x.pdf")
    assert ex.status == "pending"
    assert ex.overall_risk == "UNKNOWN"
