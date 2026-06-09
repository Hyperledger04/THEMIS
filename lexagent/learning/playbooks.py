"""
Playbook note capture and retrieval — matter-type and court-specific observations.

Playbook notes are institutional knowledge accumulated from repeated patterns:
  - A specific court's preferred citation format.
  - Procedural pitfalls in a particular High Court.
  - Limitation doctrines that recur in a matter type.

They are stored explicitly, tied to provenance, and reviewed before surfacing —
never silently injected without the lawyer having seen them first.

§8C rule: playbook notes are SUGGESTIONS. They never overwrite skill files or
core system prompts automatically. The skill-update workflow (Phase 13) is the
path from a playbook note to a permanent skill change.
"""
from __future__ import annotations

import logging
from typing import Optional

from lexagent.workspace.models import PlaybookNote

logger = logging.getLogger(__name__)


def record_playbook_note(
    repo,
    firm_id: str,
    observation: str,
    matter_type: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    court: Optional[str] = None,
    source_feedback_ids: Optional[list[str]] = None,
) -> PlaybookNote:
    """Persist a single playbook observation with full provenance.

    Args:
        repo:                PostgresWorkspaceRepository.
        firm_id:             Tenant scope.
        observation:         The actionable observation (one sentence).
        matter_type:         Matter type this applies to (writ, arbitration, etc.).
        jurisdiction:        Jurisdiction code (e.g. "india", "karnataka_hc").
        court:               Specific court name if applicable.
        source_feedback_ids: Feedback IDs that evidence this observation.
    """
    note = PlaybookNote(
        firm_id=firm_id,
        observation=observation,
        matter_type=matter_type,
        jurisdiction=jurisdiction,
        court=court,
        source_feedback_ids=source_feedback_ids or [],
    )
    repo.create_playbook_note(note)
    logger.info(
        "Recorded playbook note %s for firm=%s matter_type=%s",
        note.note_id, firm_id, matter_type,
    )
    return note


def get_playbook_context(
    repo,
    firm_id: str,
    matter_type: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    court: Optional[str] = None,
) -> str:
    """Return a formatted playbook context block for injection into prompts.

    Used by the planner and drafting nodes to surface court- and matter-type-
    specific institutional knowledge before generating DAGs or drafts.
    Returns an empty string when no notes exist.
    """
    notes = repo.list_playbook_notes(
        firm_id=firm_id,
        matter_type=matter_type,
        jurisdiction=jurisdiction,
        court=court,
    )
    if not notes:
        return ""

    heading_parts = ["## Firm Playbook Notes"]
    if matter_type:
        heading_parts.append(f"({matter_type}")
    if court:
        heading_parts.append(f"— {court})")
    elif matter_type:
        heading_parts.append(")")

    lines = [" ".join(heading_parts)]
    for note in notes:
        lines.append(f"- {note.observation}")
    lines.append(
        "\n_These observations were recorded from prior matters. "
        "Verify against current court practice before relying on them._"
    )
    return "\n".join(lines)


def suggest_playbook_update(
    repo,
    llm_call,
    firm_id: str,
    matter_type: str,
    feedback_sample: list,
    jurisdiction: Optional[str] = None,
) -> list[str]:
    """Use LLM to propose new playbook observations from a batch of feedback.

    Returns proposed observation strings for lawyer review — does NOT persist
    them automatically. The caller presents these to the lawyer for approval
    before calling record_playbook_note().

    §8C: This is a propose-then-approve pattern, never auto-commit.
    """
    if not feedback_sample:
        return []

    digest_lines = []
    for fb in feedback_sample[:15]:
        if fb.note:
            digest_lines.append(f"- [{fb.signal}] {fb.note}")
        if fb.diff:
            digest_lines.append(f"  Edit: {fb.diff[:400]}")

    prompt = f"""You are reviewing lawyer feedback from {matter_type} matters{' in ' + jurisdiction if jurisdiction else ''}.

Feedback sample:
{chr(10).join(digest_lines)}

Propose 2–4 playbook observations that would help future work on similar matters.
Rules:
- Each observation must be factual and actionable, not generic advice.
- Focus on court-specific procedural patterns, limitation quirks, or recurring drafting issues.
- Do NOT propose observations about legal substance (courts decide that, not playbooks).
- Do NOT propose anything that contradicts statute or settled Supreme Court practice.

Respond with a numbered list, one observation per line. No preamble."""

    try:
        raw = llm_call(prompt)
    except Exception as exc:
        logger.warning("LLM call for playbook suggestion failed: %s", exc)
        return []

    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    proposals = []
    for line in lines:
        for prefix in ("1.", "2.", "3.", "4.", "-", "•"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if line:
            proposals.append(line)
    return proposals[:4]
