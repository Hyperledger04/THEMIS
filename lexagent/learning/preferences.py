"""
Style preference extraction from lawyer feedback.

When a lawyer edits a draft (signal=edited, diff present) or explicitly prefers
a style (signal=preferred), this module extracts a reusable drafting preference
and stores it for future injection. The LLM call is explicit and reviewable —
not a silent background rewrite.

§8C rule: preferences are SUGGESTIONS injected into context, not permanent
rewrites of core prompts or skill files.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from lexagent.workspace.models import FeedbackItem, StylePreference

logger = logging.getLogger(__name__)


def extract_style_preferences(
    repo,
    llm_call,
    user_id: str,
    firm_id: str,
    matter_type: Optional[str] = None,
    doc_type: Optional[str] = None,
    max_feedback: int = 10,
) -> list[StylePreference]:
    """Extract and store style preferences from recent edited/preferred feedback.

    Runs an LLM pass over recent diffs and notes to identify reusable patterns.
    Only processes feedback with a diff or a note — no inference from raw signal alone.

    Args:
        repo:         PostgresWorkspaceRepository.
        llm_call:     Async callable (prompt: str) -> str for preference extraction.
        user_id:      Whose preferences to extract.
        firm_id:      Tenant scope.
        matter_type:  Scope extraction to a specific matter type (optional).
        doc_type:     Scope to a specific document type (optional).
        max_feedback: Maximum feedback items to process in one pass.

    Returns:
        List of StylePreference objects that were upserted into the DB.
    """
    items = repo.list_feedback(
        user_id=user_id,
        firm_id=firm_id,
        target_type="draft",
        limit=max_feedback,
    )
    # Only items with actual edit content are useful for style extraction.
    actionable = [fb for fb in items if fb.diff or fb.note]
    if not actionable:
        logger.debug("No actionable feedback found for preference extraction.")
        return []

    digest = _build_feedback_digest(actionable)
    prompt = _preference_extraction_prompt(digest, matter_type, doc_type)

    try:
        raw = llm_call(prompt)
    except Exception as exc:
        logger.warning("LLM call for preference extraction failed: %s", exc)
        return []

    # Parse bullet-point preferences from LLM output.
    preference_texts = _parse_preferences(raw)
    if not preference_texts:
        return []

    feedback_ids = [fb.feedback_id for fb in actionable]
    now = datetime.now(tz=timezone.utc).isoformat()
    prefs: list[StylePreference] = []
    for text in preference_texts:
        pref = StylePreference(
            user_id=user_id,
            firm_id=firm_id,
            matter_type=matter_type,
            doc_type=doc_type,
            preference_text=text,
            source_feedback_ids=feedback_ids,
            updated_at=now,
        )
        repo.upsert_style_preference(pref)
        prefs.append(pref)

    logger.info("Extracted %d style preferences for user %s.", len(prefs), user_id)
    return prefs


def get_style_context(
    repo,
    user_id: str,
    firm_id: str,
    matter_type: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> str:
    """Return an injected style context block for the drafting system prompt.

    Returns an empty string when no preferences exist — the caller can include
    this block unconditionally without checking first.
    """
    prefs = repo.list_style_preferences(
        user_id=user_id,
        firm_id=firm_id,
        matter_type=matter_type,
        doc_type=doc_type,
    )
    if not prefs:
        return ""

    lines = ["## Your Drafting Style Preferences (learned from your edits)"]
    for pref in prefs:
        lines.append(f"- {pref.preference_text}")
    lines.append(
        "\n_These preferences were extracted from your accepted edits and are "
        "suggestions only — use your judgment._"
    )
    return "\n".join(lines)


def _build_feedback_digest(items: list[FeedbackItem]) -> str:
    parts = []
    for fb in items:
        parts.append(f"Signal: {fb.signal}")
        if fb.note:
            parts.append(f"Note: {fb.note}")
        if fb.diff:
            parts.append(f"Diff:\n{fb.diff[:800]}")
        parts.append("---")
    return "\n".join(parts)


def _preference_extraction_prompt(
    digest: str, matter_type: Optional[str], doc_type: Optional[str]
) -> str:
    scope = ""
    if matter_type:
        scope += f" for {matter_type} matters"
    if doc_type:
        scope += f" in {doc_type} documents"
    return f"""You are analysing a lawyer's edit history to extract reusable drafting preferences.

Context: Indian litigation practice{scope}.

Feedback digest:
{digest}

Extract 2–5 concise, actionable drafting preferences from this feedback.
Rules:
- Each preference must be a single sentence starting with an action verb.
- Preferences must be specific, not generic ("Use passive voice" is too generic).
- Only extract preferences that appear consistently across multiple edits.
- Do NOT invent preferences not supported by the edits.
- Do NOT suggest changes to legal substance — style only.

Respond with a numbered list, one preference per line. No preamble or explanation."""


def _parse_preferences(raw: str) -> list[str]:
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    prefs = []
    for line in lines:
        # Strip leading numbers / bullets (1. 2. - •)
        for prefix in ("1.", "2.", "3.", "4.", "5.", "-", "•", "*"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if line:
            prefs.append(line)
    return prefs[:5]
