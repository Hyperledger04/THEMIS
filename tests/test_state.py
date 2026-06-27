# Tests for LexState — validate the TypedDict structure and field behaviour.
# Run with: pytest tests/test_state.py -v

from typing import get_type_hints

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from themis.state import SeniorCounselState


def _minimal_state() -> SeniorCounselState:
    """Returns a minimal valid LexState with only required fields set."""
    return {
        "user_input": "I need an injunction",
        "matter_id": None,
        "matter_type": None,
        "parties": None,
        "jurisdiction": None,
        "jurisdiction_country": None,
        "purpose": None,
        "key_clauses": None,
        "tone_preference": None,
        "risks_to_address": None,
        "citations_required": None,
        "intake_complete": False,
        "clarifying_questions": None,
        "research_findings": None,
        "statutes_cited": None,
        "limitation_analysis": None,
        "document_outline": None,
        "draft_output": None,
        "risk_annotations": None,
        "plain_english_summary": None,
        "citations_verified": False,
        "unverified_citations": None,
        "messages": [],
        "lawyer_soul": None,
        "active_skill": None,
        "error": None,
        "next_node": None,
    }


class TestLexStateFields:
    def test_state_accepts_minimal_input(self):
        """LexState can be constructed with only user_input and default values."""
        state = _minimal_state()
        assert state["user_input"] == "I need an injunction"

    def test_intake_complete_defaults_to_false(self):
        state = _minimal_state()
        assert state["intake_complete"] is False

    def test_citations_verified_defaults_to_false(self):
        state = _minimal_state()
        assert state["citations_verified"] is False

    def test_optional_fields_default_to_none(self):
        state = _minimal_state()
        optional_fields = [
            "matter_id", "matter_type", "parties", "jurisdiction",
            "jurisdiction_country", "purpose", "key_clauses", "tone_preference",
            "risks_to_address", "citations_required", "clarifying_questions",
            "research_findings", "statutes_cited", "limitation_analysis",
            "document_outline", "draft_output", "risk_annotations",
            "plain_english_summary", "unverified_citations",
            "lawyer_soul", "active_skill", "error", "next_node",
        ]
        for field in optional_fields:
            assert state[field] is None, f"Expected {field} to be None, got {state[field]}"

    def test_messages_defaults_to_empty_list(self):
        state = _minimal_state()
        assert state["messages"] == []

    def test_all_required_fields_exist(self):
        """Verify LexState has all fields defined in the TypedDict."""
        hints = get_type_hints(SeniorCounselState)
        required = [
            "user_input", "intake_complete", "citations_verified", "messages",
            "matter_type", "parties", "jurisdiction", "purpose",
            "draft_output", "error",
        ]
        for field in required:
            assert field in hints, f"Expected field '{field}' in LexState"


class TestLexStateAssignment:
    def test_can_set_intake_complete(self):
        state = _minimal_state()
        state["intake_complete"] = True
        assert state["intake_complete"] is True

    def test_can_set_matter_type(self):
        state = _minimal_state()
        state["matter_type"] = "injunction application"
        assert state["matter_type"] == "injunction application"

    def test_can_set_parties_as_dict(self):
        state = _minimal_state()
        state["parties"] = {"plaintiff": "ABC Ltd", "defendant": "XYZ Developers"}
        assert state["parties"]["plaintiff"] == "ABC Ltd"

    def test_can_set_research_findings(self):
        state = _minimal_state()
        state["research_findings"] = [
            {
                "case_name": "Dalpat Kumar v. Prahlad Singh",
                "citation": "(1991) 4 SCC 130",
                "relevance": "balance of convenience test",
                "url": "https://indiankanoon.org/doc/123456",
                "source": "Indian Kanoon",
            }
        ]
        assert len(state["research_findings"]) == 1
        assert state["research_findings"][0]["citation"] == "(1991) 4 SCC 130"

    def test_can_append_messages(self):
        """Messages list can hold LangChain message objects."""
        state = _minimal_state()
        state["messages"] = [
            HumanMessage(content="I need an injunction"),
            AIMessage(content="Sure, what is the jurisdiction?"),
        ]
        assert len(state["messages"]) == 2
        assert state["messages"][0].content == "I need an injunction"


class TestLexStateJurisdictionCountry:
    def test_jurisdiction_country_is_optional(self):
        """jurisdiction_country is the global-scope addition — must be optional."""
        state = _minimal_state()
        assert state["jurisdiction_country"] is None

    def test_jurisdiction_country_can_be_set(self):
        state = _minimal_state()
        state["jurisdiction_country"] = "IN"
        assert state["jurisdiction_country"] == "IN"


class TestPhase7Fields:
    """Phase 7: workflow_mode routing and contract review fields."""

    def test_workflow_mode_field_exists(self):
        from typing import get_type_hints
        hints = get_type_hints(SeniorCounselState)
        assert "workflow_mode" in hints

    def test_contract_fields_exist(self):
        from typing import get_type_hints
        hints = get_type_hints(SeniorCounselState)
        assert "contract_upload_path" in hints
        assert "contract_risk_analysis" in hints
        assert "contract_review_output" in hints
        assert "cause_of_action_date" in hints

    def test_workflow_mode_can_be_set_to_draft(self):
        state = _minimal_state()
        state["workflow_mode"] = "draft"
        assert state["workflow_mode"] == "draft"

    def test_workflow_mode_can_be_set_to_contract_review(self):
        state = _minimal_state()
        state["workflow_mode"] = "contract_review"
        assert state["workflow_mode"] == "contract_review"

    def test_contract_upload_path_can_be_set(self):
        state = _minimal_state()
        state["contract_upload_path"] = "/tmp/agreement.pdf"
        assert state["contract_upload_path"] == "/tmp/agreement.pdf"

    def test_contract_risk_analysis_can_store_findings(self):
        state = _minimal_state()
        state["contract_risk_analysis"] = {
            "overall_risk": "HIGH",
            "findings": [{"risk_level": "HIGH", "category": "Liability"}],
            "high_count": 1,
        }
        assert state["contract_risk_analysis"]["overall_risk"] == "HIGH"
        assert len(state["contract_risk_analysis"]["findings"]) == 1

    def test_cause_of_action_date_is_iso_string(self):
        state = _minimal_state()
        state["cause_of_action_date"] = "2025-01-15"
        assert state["cause_of_action_date"] == "2025-01-15"


class TestNodeOutputPattern:
    def test_partial_dict_update_pattern(self):
        """
        Verify that the node return pattern works — nodes return partial dicts
        and we merge them into the state. This is the core LangGraph contract.
        """
        state = _minimal_state()

        # Simulate what intake.run() returns
        intake_output = {
            "matter_type": "injunction application",
            "jurisdiction": "Delhi High Court, India",
            "intake_complete": False,
            "clarifying_questions": ["Who are the parties?", "What is the purpose?"],
        }

        # Merge (as LangGraph does automatically)
        merged = {**state, **intake_output}

        assert merged["matter_type"] == "injunction application"
        assert merged["jurisdiction"] == "Delhi High Court, India"
        assert merged["intake_complete"] is False
        assert len(merged["clarifying_questions"]) == 2
        # Fields not in intake_output are unchanged
        assert merged["user_input"] == "I need an injunction"
        assert merged["draft_output"] is None
