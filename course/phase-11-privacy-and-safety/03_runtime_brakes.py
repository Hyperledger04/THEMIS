"""
Phase 11, Lesson 3 — Runtime Brakes: Cost Caps, Halt Flags, Phase Gates

Run this file: python course/phase-11-privacy-and-safety/03_runtime_brakes.py
"""

# ============================================================
# THE PROBLEM
# ============================================================
#
# A legal research agent runs overnight. It loops through 50 judgments,
# summarises each one, cross-references statutes, and emails a morning brief.
#
# By 6 AM it has made 400 LLM calls and spent $80. No one authorised that.
#
# Three independent safety mechanisms prevent this:
#   1. CostLedger  — tracks spend; halts when a cap is hit
#   2. HaltFlag    — checks for external cancellation or idle timeout
#   3. PhaseGate   — prevents tools from firing in the wrong workflow phase

from lexagent.runtime.brakes import (
    CostCapReached,
    CostLedger,
    HaltFlag,
    PhaseGate,
    PhaseViolation,
)


# ============================================================
# 1. CostLedger
# ============================================================

print("=== CostLedger ===\n")

# No caps → just tracks, never raises
ledger = CostLedger()
delta = ledger.record(input_tokens=5000, output_tokens=2000, model="anthropic/claude-sonnet-4-6")
print(f"  5k input + 2k output @ Anthropic → ${delta:.6f}")
print(f"  Job total so far: ${ledger.job_spent:.6f}")
print(f"  Session total:    ${ledger.session_spent:.6f}")
print()

# With a $0.01 job cap
print("  With job_cap_usd=0.01:")
ledger2 = CostLedger(job_cap_usd=0.01)
try:
    # This call is cheap
    ledger2.record(input_tokens=100, output_tokens=50, model="anthropic/claude-sonnet-4-6")
    print("  → First call: OK")
    # This call pushes over the cap
    ledger2.record(input_tokens=1_000_000, output_tokens=500_000, model="anthropic/claude-sonnet-4-6")
except CostCapReached as e:
    print(f"  → HALTED: {e}")
print()

# Local models are free — caps never trigger
ledger3 = CostLedger(job_cap_usd=0.00001)
delta = ledger3.record(input_tokens=1_000_000, output_tokens=1_000_000, model="ollama/llama3.2")
print(f"  Ollama (local): 1M tokens → ${delta:.2f} (free, cap never triggers)")
print()

# Session cap: carries spend across jobs
print("  Session cap: $5 with $4.99 already spent:")
ledger4 = CostLedger(session_cap_usd=5.0, session_spent_so_far=4.99)
try:
    ledger4.record(input_tokens=100_000, output_tokens=50_000, model="anthropic/claude-sonnet-4-6")
except CostCapReached as e:
    print(f"  → HALTED: {e}")


# ============================================================
# 2. HaltFlag
# ============================================================

print("\n=== HaltFlag ===\n")

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# Simulate a repo where the job is still running
running_repo = MagicMock()
running_repo.get_job_status.return_value = "running"

flag = HaltFlag(running_repo, idle_timeout_minutes=30)
result = flag.should_halt("job_001")
print(f"  Job running, last active 1 min ago → {result}")  # None = keep going

# Simulate externally cancelled job
cancelled_repo = MagicMock()
cancelled_repo.get_job_status.return_value = "cancelled"

flag2 = HaltFlag(cancelled_repo)
result2 = flag2.should_halt("job_002")
print(f"  Job externally cancelled → '{result2}'")  # "external_halt"

# Idle timeout
flag3 = HaltFlag(running_repo, idle_timeout_minutes=5)
stale_time = datetime.now(tz=timezone.utc) - timedelta(minutes=20)
result3 = flag3.should_halt("job_003", last_activity_at=stale_time)
print(f"  Job idle for 20 min (timeout=5 min) → '{result3}'")  # "idle_timeout"

print()
print("  The worker checks HaltFlag BEFORE starting each job step.")
print("  Jobs stop at safe boundaries — not mid-LLM-call.")
print()
print("  To cancel a running job from outside:")
print("  POST /api/v1/matters/{matter_id}/runs/{run_id}/halt")


# ============================================================
# 3. PhaseGate
# ============================================================

print("\n=== PhaseGate ===\n")

# Define which tools are allowed in which phases
phase_map = {
    "send_email":      ["approval_granted"],
    "file_with_court": ["approval_granted", "final_review"],
    "draft_document":  ["drafting", "revision"],
}

gate = PhaseGate(phase_map, current_phase="drafting")

# These should pass
gate.check("draft_document")
print("  'draft_document' in 'drafting' phase → ALLOWED")

gate.check("any_unlisted_tool")
print("  'any_unlisted_tool' → ALLOWED (not in phase_map = unrestricted)")

# This should fail
try:
    gate.check("send_email")  # send_email only allowed in "approval_granted"
except PhaseViolation as e:
    print(f"  'send_email' in 'drafting' phase → BLOCKED: {e}")

# Advance the phase
gate.set_phase("approval_granted")
gate.check("send_email")
print("  'send_email' in 'approval_granted' phase → ALLOWED")


# ============================================================
# HOW BRAKES WIRE INTO THE WORKER
# ============================================================
#
# lexagent/runtime/worker.py creates brakes before each job:
#
#   ledger = CostLedger(session_cap_usd=cfg.cost_cap_session_usd, ...)
#   halt_flag = HaltFlag(repo, idle_timeout_minutes=cfg.idle_timeout_minutes)
#
#   halt_reason = halt_flag.should_halt(job.job_id)
#   if halt_reason:
#       repo.cancel_job(job.job_id, reason=halt_reason)
#       return
#
#   try:
#       await handler(job, repo, ledger=ledger, halt_flag=halt_flag)
#   except CostCapReached as e:
#       repo.cancel_job(job.job_id, reason=str(e))
#
# Existing handlers that don't declare ledger/halt_flag still work —
# the worker uses inspect.signature() to pass kwargs only when accepted.

print()
print("=== Config Knobs ===")
print()
print("  LEX_COST_CAP_SESSION=5.0   → $5 session cap (0 = disabled)")
print("  LEX_COST_CAP_JOB=1.0      → $1 per-job cap")
print("  LEX_IDLE_TIMEOUT_MINUTES=30 → halt after 30 min idle")
print("  All default to 0/disabled — existing behaviour unchanged")
