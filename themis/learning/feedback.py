"""
Feedback capture and retrieval for the Learning Loop.

Feedback signals are the raw inputs to preference extraction and playbook generation.
They are stored with full provenance so any extracted preference can be traced back
to the specific feedback event that produced it and removed if wrong.
"""
from __future__ import annotations

from typing import Optional

from themis.workspace.models import FeedbackItem


def capture_feedback(
    repo,
    user_id: str,
    target_type: str,
    signal: str,
    target_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    note: Optional[str] = None,
    diff: Optional[str] = None,
) -> FeedbackItem:
    """Persist a single feedback signal and return the stored record.

    Args:
        repo:        PostgresWorkspaceRepository instance.
        user_id:     Lawyer or user who gave the feedback.
        target_type: One of draft, research, authority, risk, skill, checklist.
        signal:      accepted | rejected | edited | preferred | corrected.
        target_id:   ID of the object being rated (draft_id, authority_id, etc.).
        matter_id:   Matter context — None for firm-level or global feedback.
        note:        Free-text comment from the lawyer.
        diff:        Unified diff of the edit (for signal=edited).
    """
    item = FeedbackItem(
        user_id=user_id,
        target_type=target_type,
        signal=signal,
        target_id=target_id,
        matter_id=matter_id,
        note=note,
        diff=diff,
    )
    return repo.create_feedback(item)


def get_feedback_context(
    repo,
    user_id: str,
    firm_id: str,
    matter_id: Optional[str] = None,
    target_type: Optional[str] = None,
    signal: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Return a formatted feedback digest for injection into a prompt.

    Retrieves the most recent feedback items and formats them as a readable
    block. The drafting and planning nodes inject this so the agent knows
    what the lawyer has already accepted or rejected.
    """
    items = repo.list_feedback(
        user_id=user_id,
        firm_id=firm_id,
        matter_id=matter_id,
        target_type=target_type,
        signal=signal,
        limit=limit,
    )
    if not items:
        return ""

    lines = ["## Recent Lawyer Feedback"]
    for fb in items:
        note_part = f" — "{fb.note}"" if fb.note else ""
        target_part = f" on {fb.target_type} {fb.target_id}" if fb.target_id else f" on {fb.target_type}"
        lines.append(f"- [{fb.signal.upper()}]{target_part}{note_part}")

    return "\n".join(lines)


def summarise_accepted_authorities(
    repo,
    user_id: str,
    firm_id: str,
    limit: int = 30,
) -> list[str]:
    """Return target_ids of authorities the lawyer has explicitly accepted.

    Used by Research Counsel to weight retrieval toward previously accepted
    precedents before starting a new research run on the same matter type.
    """
    items = repo.list_feedback(
        user_id=user_id,
        firm_id=firm_id,
        target_type="authority",
        signal="accepted",
        limit=limit,
    )
    return [fb.target_id for fb in items if fb.target_id]
