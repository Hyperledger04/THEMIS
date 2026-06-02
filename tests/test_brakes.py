"""Tests for lexagent/runtime/brakes.py — CostLedger, HaltFlag, PhaseGate."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from lexagent.runtime.brakes import (
    CostCapReached,
    CostLedger,
    HaltFlag,
    PhaseGate,
    PhaseViolation,
)


# ---------------------------------------------------------------------------
# CostLedger
# ---------------------------------------------------------------------------

def test_cost_ledger_noop_when_caps_zero():
    """No caps set — record() should accumulate without raising."""
    ledger = CostLedger()
    delta = ledger.record(input_tokens=1000, output_tokens=500, model="anthropic/claude-sonnet-4-6")
    assert delta > 0
    assert ledger.job_spent > 0


def test_cost_ledger_job_cap_raises():
    ledger = CostLedger(job_cap_usd=0.000001)  # vanishingly small cap
    with pytest.raises(CostCapReached) as exc_info:
        ledger.record(input_tokens=10000, output_tokens=5000, model="anthropic/claude-sonnet-4-6")
    assert exc_info.value.scope == "job"
    assert exc_info.value.limit == 0.000001


def test_cost_ledger_session_cap_raises():
    ledger = CostLedger(session_cap_usd=0.000001, session_spent_so_far=0.000001)
    with pytest.raises(CostCapReached) as exc_info:
        ledger.record(input_tokens=100, output_tokens=50, model="anthropic/claude-sonnet-4-6")
    assert exc_info.value.scope == "session"


def test_cost_ledger_session_spent_accumulates():
    ledger = CostLedger(session_spent_so_far=1.0)
    ledger.record(input_tokens=1000, output_tokens=500, model="anthropic/claude-sonnet-4-6")
    assert ledger.session_spent > 1.0


def test_cost_ledger_zero_cost_for_local_model():
    ledger = CostLedger(job_cap_usd=0.001)
    delta = ledger.record(input_tokens=100_000, output_tokens=50_000, model="ollama/llama3.2")
    assert delta == 0.0  # local models are free


def test_cost_ledger_unknown_provider_uses_default_rate():
    ledger = CostLedger()
    delta = ledger.record(input_tokens=1_000_000, output_tokens=0, model="unknown/model")
    # Default rate is $3/M input tokens
    assert abs(delta - 3.0) < 0.01


# ---------------------------------------------------------------------------
# HaltFlag
# ---------------------------------------------------------------------------

def _make_repo(status: str = "running"):
    repo = MagicMock()
    repo.get_job_status.return_value = status
    return repo


def test_halt_flag_none_when_running():
    flag = HaltFlag(_make_repo("running"), idle_timeout_minutes=0)
    result = flag.should_halt("job_123")
    assert result is None


def test_halt_flag_external_halt_when_cancelled():
    flag = HaltFlag(_make_repo("cancelled"), idle_timeout_minutes=0)
    result = flag.should_halt("job_123")
    assert result == "external_halt"


def test_halt_flag_idle_timeout():
    repo = _make_repo("running")
    flag = HaltFlag(repo, idle_timeout_minutes=5)
    old_time = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    result = flag.should_halt("job_123", last_activity_at=old_time)
    assert result == "idle_timeout"


def test_halt_flag_no_idle_timeout_when_recent():
    repo = _make_repo("running")
    flag = HaltFlag(repo, idle_timeout_minutes=30)
    recent_time = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    result = flag.should_halt("job_123", last_activity_at=recent_time)
    assert result is None


def test_halt_flag_idle_disabled_when_zero():
    repo = _make_repo("running")
    flag = HaltFlag(repo, idle_timeout_minutes=0)
    old_time = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    result = flag.should_halt("job_123", last_activity_at=old_time)
    assert result is None  # idle check disabled


def test_halt_flag_repo_exception_does_not_halt():
    """DB errors should not halt jobs — prefer false negative over false positive."""
    repo = MagicMock()
    repo.get_job_status.side_effect = Exception("DB down")
    flag = HaltFlag(repo, idle_timeout_minutes=0)
    result = flag.should_halt("job_123")
    assert result is None


def test_halt_flag_handles_naive_datetime():
    """Naive datetime (no tzinfo) should be treated as UTC without error."""
    repo = _make_repo("running")
    flag = HaltFlag(repo, idle_timeout_minutes=5)
    old_time = datetime.utcnow() - timedelta(minutes=10)  # naive UTC
    result = flag.should_halt("job_123", last_activity_at=old_time)
    assert result == "idle_timeout"


# ---------------------------------------------------------------------------
# PhaseGate
# ---------------------------------------------------------------------------

def test_phase_gate_empty_map_allows_all():
    gate = PhaseGate({}, current_phase="drafting")
    gate.check("send_email")  # should not raise


def test_phase_gate_allows_tool_in_correct_phase():
    gate = PhaseGate({"send_email": ["approval_granted"]}, current_phase="approval_granted")
    gate.check("send_email")  # should not raise


def test_phase_gate_blocks_tool_in_wrong_phase():
    gate = PhaseGate({"send_email": ["approval_granted"]}, current_phase="drafting")
    with pytest.raises(PhaseViolation) as exc_info:
        gate.check("send_email")
    assert exc_info.value.tool_name == "send_email"
    assert exc_info.value.current_phase == "drafting"
    assert "approval_granted" in exc_info.value.allowed_phases


def test_phase_gate_unrestricted_tool_always_passes():
    gate = PhaseGate({"send_email": ["approval_granted"]}, current_phase="init")
    gate.check("some_other_tool")  # not in phase_map → allowed


def test_phase_gate_set_phase_changes_enforcement():
    gate = PhaseGate({"send_email": ["approved"]}, current_phase="drafting")
    with pytest.raises(PhaseViolation):
        gate.check("send_email")
    gate.set_phase("approved")
    gate.check("send_email")  # should now pass


def test_phase_violation_attributes():
    exc = PhaseViolation("my_tool", "init", ["phase_a", "phase_b"])
    assert exc.tool_name == "my_tool"
    assert exc.current_phase == "init"
    assert exc.allowed_phases == ["phase_a", "phase_b"]
    assert "my_tool" in str(exc)
