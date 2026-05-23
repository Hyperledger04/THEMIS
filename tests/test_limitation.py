"""Tests for the Indian Limitation Act calculator."""

import pytest
from lexagent.tools.limitation import check_limitation


def test_civil_suit_returns_three_years():
    result = check_limitation("civil suit")
    assert result["limitation_years"] == 3


def test_property_suit_returns_twelve_years():
    result = check_limitation("property suit")
    assert result["limitation_years"] == 12


def test_cheque_dishonour_returns_one_year():
    result = check_limitation("cheque dishonour")
    assert result["limitation_years"] == 1


def test_writ_petition_has_no_fixed_period():
    result = check_limitation("writ petition")
    assert result["limitation_years"] is None


def test_unknown_matter_type_falls_back_to_default():
    result = check_limitation("something obscure")
    assert result["limitation_years"] == 3


def test_expired_risk_when_deadline_passed():
    result = check_limitation("civil suit", cause_of_action_date="2020-01-01")
    assert result["risk"] == "expired"


def test_clear_risk_for_recent_cause_of_action():
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=30)).isoformat()
    result = check_limitation("civil suit", cause_of_action_date=recent)
    assert result["risk"] == "clear"


def test_within_6_months_risk():
    from datetime import date, timedelta
    # Set cause of action so deadline is ~3 months away
    # civil suit = 3 years; so coa 3 years ago minus 3 months
    coa = (date.today() - timedelta(days=3 * 365 - 90)).isoformat()
    result = check_limitation("civil suit", cause_of_action_date=coa)
    assert result["risk"] == "within_6_months"


def test_analysis_is_non_empty_string():
    result = check_limitation("injunction")
    assert isinstance(result["analysis"], str)
    assert len(result["analysis"]) > 10


def test_result_has_all_keys():
    result = check_limitation("civil suit", cause_of_action_date="2023-01-01")
    required_keys = {
        "matter_type", "limitation_years", "legal_basis", "note",
        "deadline", "risk", "analysis",
    }
    assert required_keys.issubset(result.keys())


def test_deadline_is_iso_date_string():
    result = check_limitation("civil suit", cause_of_action_date="2023-06-15")
    assert result["deadline"] == "2026-06-15"


def test_no_deadline_when_no_coa_date():
    result = check_limitation("civil suit")
    assert result["deadline"] is None


def test_invalid_date_does_not_crash():
    result = check_limitation("civil suit", cause_of_action_date="not-a-date")
    assert result["risk"] == "unknown"
