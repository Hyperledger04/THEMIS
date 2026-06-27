# Debate board — mcp__lex__ server (§7 of V3 architecture).
#
# PURPOSE: Errors are caught at the finding level, not the final draft.
# ResearcherAgent posts findings → ReviewerAgent challenges weak ones →
# debate resolves → DrafterAgent sees only resolved, high-confidence findings.
#
# V3.3 implementation: in-memory store backed by a thread-safe dict.
# V3.4 migration: swap _store for a Postgres `debate_board` table query.
# The tool function signatures never change — callers are unaffected.
#
# WHY not use the `mcp` package yet: `mcp` is not in pyproject.toml for V3.3.
# This module exposes the debate board as plain async functions callable by any
# specialist node. When `mcp` is added (V3.4), a thin FastMCP wrapper is added
# at the bottom — the function bodies stay identical.

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# In-memory store (replaced by Postgres in V3.4)
# ---------------------------------------------------------------------------

_store: dict[str, list[dict]] = {}   # keyed by matter_id
_lock = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matter_board(matter_id: str) -> list[dict]:
    """Return the finding list for matter_id, creating it if needed."""
    with _lock:
        if matter_id not in _store:
            _store[matter_id] = []
        return _store[matter_id]


# ---------------------------------------------------------------------------
# Public tool functions (called by specialist nodes; exposed via MCP in V3.4)
# ---------------------------------------------------------------------------


def post_finding(
    matter_id: str,
    agent_id: str,
    finding_text: str,
    confidence: float,
    evidence_refs: Optional[list[str]] = None,
) -> dict:
    """
    Post a research finding to the debate board.

    Args:
        matter_id:     Scopes the finding to one matter.
        agent_id:      Which specialist posted this (e.g. "researcher").
        finding_text:  The legal proposition being asserted.
        confidence:    0.0–1.0. Below 0.5 → use decline_to_find instead.
        evidence_refs: List of citation strings or document IDs supporting this finding.

    Returns:
        {"finding_id": str, "status": "open"}
    """
    if confidence < 0.5:
        raise ValueError(
            f"Confidence {confidence} below 0.5 — use decline_to_find() instead."
        )

    finding = {
        "finding_id": str(uuid.uuid4()),
        "matter_id": matter_id,
        "agent_id": agent_id,
        "finding_text": finding_text,
        "confidence": confidence,
        "evidence_refs": evidence_refs or [],
        "status": "open",
        "challenges": [],
        "created_at": _now(),
    }
    _matter_board(matter_id).append(finding)
    return {"finding_id": finding["finding_id"], "status": "open"}


def decline_to_find(
    matter_id: str,
    agent_id: str,
    reason: str,
    matter_area: str,
) -> dict:
    """
    Log a declined finding — used when confidence < 0.5.
    Triggers human review rather than a hallucinated finding.

    Returns:
        {"declined_id": str, "status": "declined", "requires_human_review": True}
    """
    declined = {
        "finding_id": str(uuid.uuid4()),
        "matter_id": matter_id,
        "agent_id": agent_id,
        "finding_text": None,
        "confidence": 0.0,
        "matter_area": matter_area,
        "status": "declined",
        "reason": reason,
        "challenges": [],
        "created_at": _now(),
    }
    _matter_board(matter_id).append(declined)
    return {
        "declined_id": declined["finding_id"],
        "status": "declined",
        "requires_human_review": True,
    }


def post_challenge(
    matter_id: str,
    agent_id: str,
    finding_id: str,
    challenge_text: str,
) -> dict:
    """
    Challenge an existing finding (e.g. ReviewerAgent challenges a weak citation).

    Returns:
        {"challenge_id": str, "finding_id": str}
    """
    board = _matter_board(matter_id)
    for finding in board:
        if finding["finding_id"] == finding_id:
            challenge = {
                "challenge_id": str(uuid.uuid4()),
                "agent_id": agent_id,
                "challenge_text": challenge_text,
                "responses": [],
                "created_at": _now(),
            }
            finding["challenges"].append(challenge)
            finding["status"] = "challenged"
            return {"challenge_id": challenge["challenge_id"], "finding_id": finding_id}

    raise ValueError(f"Finding {finding_id} not found in matter {matter_id}")


def post_response(
    matter_id: str,
    agent_id: str,
    challenge_id: str,
    response_text: str,
) -> dict:
    """
    Respond to a challenge. If the response is accepted, finding status → 'resolved'.

    Returns:
        {"response_id": str, "challenge_id": str}
    """
    board = _matter_board(matter_id)
    for finding in board:
        for challenge in finding.get("challenges", []):
            if challenge["challenge_id"] == challenge_id:
                response = {
                    "response_id": str(uuid.uuid4()),
                    "agent_id": agent_id,
                    "response_text": response_text,
                    "created_at": _now(),
                }
                challenge["responses"].append(response)
                # Auto-resolve when a response is posted (full resolution logic in V3.4)
                if finding["status"] == "challenged":
                    finding["status"] = "resolved"
                return {"response_id": response["response_id"], "challenge_id": challenge_id}

    raise ValueError(f"Challenge {challenge_id} not found in matter {matter_id}")


def get_findings(
    matter_id: str,
    status: Optional[Literal["open", "challenged", "resolved", "declined"]] = None,
) -> list[dict]:
    """
    Return all findings for a matter, optionally filtered by status.
    DrafterAgent calls this to see only resolved, high-confidence findings.
    """
    board = _matter_board(matter_id)
    if status:
        return [f for f in board if f["status"] == status]
    return list(board)


def get_debate_summary(matter_id: str) -> dict:
    """
    Return a summary of the debate board state for a matter.
    Senior Counsel calls this before deciding to proceed or interrupt for review.
    """
    board = _matter_board(matter_id)
    by_status: dict[str, int] = {}
    for finding in board:
        s = finding["status"]
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "matter_id": matter_id,
        "total_findings": len(board),
        "by_status": by_status,
        "has_unresolved": any(f["status"] in ("open", "challenged") for f in board),
        "has_declined": any(f["status"] == "declined" for f in board),
    }


def get_unresolved_debates(matter_id: str) -> list[dict]:
    """
    Return findings that are still open or challenged — Senior Counsel checks this
    before allowing DrafterAgent to proceed. Unresolved findings require human review.
    """
    board = _matter_board(matter_id)
    return [f for f in board if f["status"] in ("open", "challenged")]


def clear_board(matter_id: str) -> None:
    """
    Clear the debate board for a matter. Called at run end to free memory.
    WHY: In-process research caches must be scoped to thread_id/matter_id and
    cleared at run completion (Key Invariant §10 of V3 architecture).
    """
    with _lock:
        _store.pop(matter_id, None)
