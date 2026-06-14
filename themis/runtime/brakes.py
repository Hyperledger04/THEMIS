"""
Agent runtime brakes — cost caps, external halt, idle watchdog, phase-gated tools.

Three independent safety mechanisms that can be composed:

  CostLedger  — tracks per-model token spend; raises CostCapReached when a cap is hit
  HaltFlag    — checks DB for external cancellation or idle timeout; returns halt reason
  PhaseGate   — restricts which tools are callable in each declared workflow phase

All three are designed to be no-ops when not configured (cap=0, empty phase_map, etc.)
so existing jobs that predate this module are unaffected.

WHY: Uninstructed LLM loops can run for hours and rack up large API bills. These brakes
give operators a safety net without requiring changes to individual agent handlers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CostCapReached(Exception):
    """Raised when accumulated cost exceeds a configured cap."""

    def __init__(self, scope: str, limit: float, actual: float) -> None:
        self.scope = scope    # "session" or "job"
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Cost cap reached ({scope}): ${actual:.4f} exceeds limit ${limit:.4f}"
        )


class PhaseViolation(Exception):
    """Raised when a tool is called outside its permitted phase."""

    def __init__(self, tool_name: str, current_phase: str, allowed_phases: list[str]) -> None:
        self.tool_name = tool_name
        self.current_phase = current_phase
        self.allowed_phases = allowed_phases
        super().__init__(
            f"Tool '{tool_name}' is not allowed in phase '{current_phase}'. "
            f"Allowed phases: {allowed_phases}"
        )


# ---------------------------------------------------------------------------
# Per-model token rate table (input, output) in USD per million tokens
# Approximate 2025 values — same table as gateway/inference.py
# ---------------------------------------------------------------------------
_RATES: dict[str, tuple[float, float]] = {
    "anthropic":  (3.0, 15.0),
    "openai":     (2.5, 10.0),
    "gemini":     (1.25, 5.0),
    "groq":       (0.05, 0.08),
    "deepseek":   (0.14, 0.28),
    "mistral":    (2.0, 6.0),
    "ollama":     (0.0, 0.0),
    "lmstudio":   (0.0, 0.0),
    "together":   (0.2, 0.2),
    "bedrock":    (3.0, 15.0),
    "azure":      (2.5, 10.0),
    "nvidia":     (1.0, 4.0),
}


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    provider = model.split("/")[0] if "/" in model else "anthropic"
    rates = _RATES.get(provider, (3.0, 15.0))
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000


# ---------------------------------------------------------------------------
# CostLedger
# ---------------------------------------------------------------------------

class CostLedger:
    """
    Tracks accumulated spend for a single job and optionally for the whole session.

    record() is called after every LLM call with the actual token counts and model.
    It raises CostCapReached immediately when either cap is exceeded.

    cap=0.0 means "no cap" — record() becomes a no-op for that scope.
    """

    def __init__(
        self,
        session_cap_usd: float = 0.0,
        job_cap_usd: float = 0.0,
        session_spent_so_far: float = 0.0,
    ) -> None:
        self._session_cap = session_cap_usd
        self._job_cap = job_cap_usd
        self._session_spent = session_spent_so_far  # accumulated before this job
        self._job_spent: float = 0.0

    @property
    def job_spent(self) -> float:
        return self._job_spent

    @property
    def session_spent(self) -> float:
        return self._session_spent + self._job_spent

    def record(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """
        Accumulate cost for one LLM call. Returns the cost delta in USD.
        Raises CostCapReached if either cap is now exceeded.
        """
        delta = _cost_usd(model, input_tokens, output_tokens)
        self._job_spent += delta

        if self._job_cap > 0 and self._job_spent > self._job_cap:
            raise CostCapReached("job", self._job_cap, self._job_spent)

        total_session = self._session_spent + self._job_spent
        if self._session_cap > 0 and total_session > self._session_cap:
            raise CostCapReached("session", self._session_cap, total_session)

        return delta


# ---------------------------------------------------------------------------
# HaltFlag
# ---------------------------------------------------------------------------

class HaltFlag:
    """
    Checks two conditions that warrant stopping a running job:

      1. External cancellation: agent_jobs.status == 'cancelled' in the DB
      2. Idle timeout: last_activity_at is more than idle_timeout_minutes ago

    should_halt() returns None (keep going) or a halt reason string.
    Pass idle_timeout_minutes=0 to disable the idle check.

    WHY a separate class instead of inline worker logic:
      Operators can call the halt API while the job is mid-step. The worker
      polls this flag at the start of each step so the job stops cleanly at
      a safe boundary rather than mid-LLM-call.
    """

    def __init__(self, repo, idle_timeout_minutes: int = 0) -> None:
        self._repo = repo
        self._idle_timeout_minutes = idle_timeout_minutes

    def should_halt(
        self,
        job_id: str,
        last_activity_at: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Returns None to continue, or a reason string to stop.
        Reasons: "external_halt" | "idle_timeout"
        """
        # Check for external cancellation in the database
        try:
            status = self._repo.get_job_status(job_id)
            if status == "cancelled":
                return "external_halt"
        except Exception:
            pass  # DB unavailable — don't halt on uncertainty

        # Check idle timeout
        if self._idle_timeout_minutes > 0 and last_activity_at is not None:
            now = datetime.now(tz=timezone.utc)
            # Normalise naive datetime to UTC-aware for safe comparison
            if last_activity_at.tzinfo is None:
                last_activity_at = last_activity_at.replace(tzinfo=timezone.utc)
            elapsed_minutes = (now - last_activity_at).total_seconds() / 60
            if elapsed_minutes >= self._idle_timeout_minutes:
                return "idle_timeout"

        return None


# ---------------------------------------------------------------------------
# PhaseGate
# ---------------------------------------------------------------------------

class PhaseGate:
    """
    Restricts tool access to declared workflow phases.

    phase_map is a dict mapping tool names to the list of phases in which
    they are permitted:  {"send_email": ["approval_granted"], "draft": ["drafting"]}

    Empty phase_map (the default) means no enforcement — all tools are allowed
    in all phases. This is the backward-compatible default for existing jobs.

    WHY: Multi-step legal workflows have stages where certain tools must not fire.
    A drafting agent must not send emails; a verification agent must not modify
    the draft. PhaseGate makes these invariants explicit and testable.
    """

    def __init__(self, phase_map: dict[str, list[str]], current_phase: str = "init") -> None:
        self._phase_map = phase_map
        self._current_phase = current_phase

    def set_phase(self, phase: str) -> None:
        self._current_phase = phase

    def check(self, tool_name: str) -> None:
        """
        Raise PhaseViolation if tool_name is not allowed in current_phase.
        No-op if phase_map is empty or tool_name is not in phase_map.
        """
        if not self._phase_map:
            return
        allowed_phases = self._phase_map.get(tool_name)
        if allowed_phases is None:
            return  # tool not in phase_map → unrestricted
        if self._current_phase not in allowed_phases:
            raise PhaseViolation(tool_name, self._current_phase, allowed_phases)
