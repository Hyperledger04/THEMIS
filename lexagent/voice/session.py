# lexagent/voice/session.py — Voice session management.
#
# WHY: Voice is a multi-turn conversation (one question per utterance).
# VoiceSession mirrors TelegramSession — it holds:
#   - The current matter_id (maps to LangGraph thread_id checkpoint)
#   - The graph_state snapshot (updated after each node runs)
#   - The queue of pending clarifying questions
#   - Flags for what the session is currently waiting for
#
# VoiceSessionStore is a simple in-memory dict keyed by session_id
# (Twilio Call SID or a UUID for WebSocket sessions). For production,
# this can be replaced with Redis or backed by Postgres.

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceSession:
    """
    Per-call / per-WebSocket-connection session state.

    Fields:
        session_id   — Twilio Call SID or browser-generated UUID
        matter_id    — LangGraph thread_id for this matter (e.g. "M-ABCD1234")
        channel      — "twilio" | "websocket"
        graph_state  — Latest merged LangGraph state dict
        completed    — True once draft_output is set
        pending_questions — Structured question objects from intake node
        awaiting_free_text_for — Field name the session is waiting text for
        turn_count   — Number of voice turns completed (for analytics)
    """
    session_id: str
    matter_id: str
    channel: str = "websocket"              # "twilio" | "websocket"
    graph_state: Optional[dict] = None
    completed: bool = False
    pending_questions: list = field(default_factory=list)
    awaiting_free_text_for: Optional[str] = None
    turn_count: int = 0

    def next_question_text(self) -> Optional[str]:
        """
        Pop and return the text of the next pending question, or None.

        WHY: Voice delivers questions one at a time — no inline keyboard,
        just speech. We pop from the queue and speak the question text.
        """
        if not self.pending_questions:
            return None
        q = self.pending_questions.pop(0)
        field_name = q.get("field", "")
        question_text = q.get("question") or q.get("label") or ""

        qtype = q.get("type", "open")
        options = q.get("options", [])

        # For binary/MCQ questions, append options to the spoken text
        # WHY: Users can't see buttons — we must speak the options aloud
        if qtype == "binary":
            question_text += " Please say yes or no."
        elif qtype == "mcq" and options:
            opts_spoken = ", ".join(options[:4])
            question_text += f" Your options are: {opts_spoken}. Or say other to enter your own."

        # Remember what field the next free-text message answers
        self.awaiting_free_text_for = field_name
        return question_text

    def update_from_node_state(self, node_state: dict) -> None:
        """Merge a LangGraph node output into the session's graph_state snapshot."""
        if self.graph_state is None:
            self.graph_state = {}
        self.graph_state.update(node_state)

        # Sync pending questions from the latest node output
        new_qs = node_state.get("pending_questions")
        if new_qs and not node_state.get("intake_complete"):
            self.pending_questions = list(new_qs)

        if node_state.get("draft_output") or node_state.get("contract_review_output"):
            self.completed = True


class VoiceSessionStore:
    """
    In-memory store mapping session_id → VoiceSession.

    WHY in-memory: Voice calls are ephemeral (< 30 min). The LangGraph
    Postgres/MemorySaver checkpointer is the durable source of truth for
    matter state. We only need fast per-call working memory here.
    """

    def __init__(self) -> None:
        self._store: dict[str, VoiceSession] = {}

    def get_or_create(
        self,
        session_id: str,
        channel: str = "websocket",
    ) -> VoiceSession:
        """Return existing session or create a new one."""
        if session_id in self._store:
            return self._store[session_id]

        matter_id = f"M-{uuid.uuid4().hex[:8].upper()}"
        session = VoiceSession(
            session_id=session_id,
            matter_id=matter_id,
            channel=channel,
        )
        self._store[session_id] = session
        return session

    def get(self, session_id: str) -> Optional[VoiceSession]:
        return self._store.get(session_id)

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)

    def list_active(self) -> list[VoiceSession]:
        return [s for s in self._store.values() if not s.completed]

    def __len__(self) -> int:
        return len(self._store)


# Module-level singleton — shared across all request handlers
_store = VoiceSessionStore()


def get_voice_session_store() -> VoiceSessionStore:
    """Return the module-level VoiceSessionStore singleton."""
    return _store
