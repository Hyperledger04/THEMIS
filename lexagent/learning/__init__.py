"""
LexAgent Learning Loop — Phase 6.

Captures lawyer feedback, extracts style preferences, and builds playbook notes.
Learning is explicit, reviewable, and reversible (§8C rule):
  - Core prompts are never silently rewritten.
  - Style preferences and playbook notes are surfaced as suggestions first.
  - Every signal is stored with provenance so bad feedback can be removed.
"""
from lexagent.learning.feedback import capture_feedback, get_feedback_context
from lexagent.learning.preferences import extract_style_preferences, get_style_context
from lexagent.learning.playbooks import record_playbook_note, get_playbook_context

__all__ = [
    "capture_feedback",
    "get_feedback_context",
    "extract_style_preferences",
    "get_style_context",
    "record_playbook_note",
    "get_playbook_context",
]
