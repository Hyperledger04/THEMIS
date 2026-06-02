"""
Phase 10 — 02: Event-Driven Runtime
=====================================
Run:  pip install pydantic
      python 02_event_driven_runtime.py

Today LexAgent runs a graph when the lawyer sends a message, produces output,
and stops.  Each run is isolated.  There is no communication between runs.

This means:
  - If a document is uploaded while a graph run is in progress, the graph
    never finds out.
  - If a limitation deadline passes at midnight, nobody is notified.
  - If Client A's morning brief is ready, there is no mechanism to push it.

V3 fixes this with a domain event system.  Every mutation in the system emits
an event.  Subscribers — other agents, notification handlers, audit loggers —
react to events without being coupled to the emitter.

This is the foundation for the 24/7 background worker (Lesson 03) and the
multi-agent chamber (Lesson 04).  Without events, those systems have no way
to coordinate.
"""

# ── SECTION 1: WHY EVENTS? — THE ISOLATION PROBLEM ──────────────────────────
#
# Imagine a law firm's morning:
#   08:00 — Paralegal uploads 150 pages of bank records for matter_001
#   08:05 — Agent begins processing the documents (background job)
#   08:47 — Agent finishes extracting 23 facts and 3 cheque dates
#   08:48 — Agent discovers that limitation expires on 10-Jun-2026 (10 days away)
#   08:49 — Agent completes a morning brief
#
# In today's LexAgent: none of this happens automatically.
# The graph only runs when the lawyer sends a message.
# The paralegal's upload is not connected to the graph at all.
#
# In V3:
#   Paralegal uploads → NEW_DOCUMENT event emitted
#   Worker picks up NEW_DOCUMENT → processes docs → DOCUMENT_PROCESSED event
#   Limitation module reacts to DOCUMENT_PROCESSED → LIMITATION_WARNING event
#   Notification handler reacts to LIMITATION_WARNING → Telegram alert sent
#   Morning brief generator reacts → MORNING_BRIEF_READY event → brief sent
#
# Each component only knows about events — not about each other.
# You can add a new subscriber (e.g., a Slack notifier) without changing
# the document processor at all.

import asyncio
import uuid
from datetime import datetime
from typing import Callable, Optional

from pydantic import BaseModel, Field


# ── SECTION 2: THE LEXICO EVENT MODEL ────────────────────────────────────────
#
# Every event in LexAgent V3 has the same envelope.
# The payload is a dict because different event types carry different data.
#
# event_id   — unique ID for this event; used for deduplication
# firm_id    — which firm this event belongs to (multi-tenancy)
# matter_id  — which matter (optional; some events are firm-wide)
# actor      — who caused this event:
#              "user"   — lawyer or paralegal took an action
#              "agent"  — an agent node caused this
#              "system" — scheduled job or background worker caused this
# type       — event name in UPPER_SNAKE_CASE (see Section 3)
# payload    — event-specific data (structured in Section 3)
# created_at — ISO timestamp; used for ordering and audit logs
# causation_id — ID of the parent event that triggered this one.
#               Allows reconstructing chains: NEW_DOCUMENT → DOCUMENT_PROCESSED
#               → LIMITATION_WARNING → MORNING_BRIEF_READY
#               WHY: legal audit trails require being able to answer
#               "why did the agent send this alert?" with a full event chain.

class LexEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    firm_id: str
    matter_id: Optional[str] = None
    actor: Literal["user", "agent", "system"]
    type: str      # one of the EVENT_TYPES defined in Section 3
    payload: dict = {}
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    causation_id: Optional[str] = None  # which event caused this one


# Pydantic does not import Literal from typing automatically in all versions.
# Fix the import order:
from typing import Literal  # noqa: E402 (re-import after BaseModel usage above)
LexEvent.model_rebuild()     # revalidate after fixing the forward reference


# ── SECTION 3: CANONICAL EVENT TYPE CATALOGUE ────────────────────────────────
#
# WHY have a catalogue?
# If every developer makes up their own event names, subscribers break silently.
# The catalogue is the contract between publishers and subscribers.
#
# Convention: NOUN_VERB_PAST_TENSE (what just happened, not what should happen)
#
# NEW_DOCUMENT          — a file was uploaded to the matter
# DOCUMENT_PROCESSED    — background worker finished parsing the file
# NEW_FACT              — agent extracted a new Fact record
# NEW_CHRONOLOGY_ITEM   — agent identified a dated event for the timeline
# NEW_HEARING           — a court date was extracted or manually entered
# LIMITATION_WARNING    — limitation period is within the configured alert window
#                         (default: 30 days, configurable per matter type)
# CLIENT_MESSAGE        — client sent a message via Telegram/WhatsApp/email
# COURT_ORDER           — agent detected a new order on the cause list
# MORNING_BRIEF_READY   — morning brief compiled and ready for lawyer review
# DRAFT_COMPLETED       — agent finished producing a draft document
# DRAFT_APPROVED        — lawyer approved a draft (human-in-the-loop gate)
# FILING_REQUESTED      — lawyer explicitly requested the agent to initiate filing
#                         (this is the ONLY way filing can be triggered)

EVENT_TYPES = {
    "NEW_DOCUMENT": "A document was uploaded to the matter workspace.",
    "DOCUMENT_PROCESSED": "Background worker finished parsing and indexing a document.",
    "NEW_FACT": "Agent extracted a new structured Fact record from source material.",
    "NEW_CHRONOLOGY_ITEM": "Agent identified a dated event for the matter timeline.",
    "NEW_HEARING": "A court date was added to the matter (by agent or manually).",
    "LIMITATION_WARNING": "Limitation period is within the configured alert window.",
    "CLIENT_MESSAGE": "Client sent an inbound message through any channel.",
    "COURT_ORDER": "Agent detected a new court order for this matter.",
    "MORNING_BRIEF_READY": "Morning brief compiled and ready for lawyer review.",
    "DRAFT_COMPLETED": "Agent finished producing a draft document.",
    "DRAFT_APPROVED": "Lawyer approved a draft — cleared for use in proceedings.",
    "FILING_REQUESTED": "Lawyer explicitly requested filing — triggers external action.",
}


# ── SECTION 4: THE IN-MEMORY EVENT BUS ───────────────────────────────────────
#
# V3's production event bus is a Postgres table + background dispatcher:
#   CREATE TABLE events (
#     event_id UUID PRIMARY KEY,
#     firm_id TEXT NOT NULL,
#     matter_id TEXT,
#     type TEXT NOT NULL,
#     payload JSONB,
#     created_at TIMESTAMPTZ DEFAULT NOW(),
#     causation_id UUID
#   );
#
# WHY Postgres before Redis/Kafka?
# 1. Every firm already has a Postgres instance (for the matter workspace).
# 2. Postgres LISTEN/NOTIFY gives push semantics without a second service.
# 3. The events table doubles as the audit log — every event is durable.
# 4. You can add Redis/Kafka later if throughput requires it; the API does not
#    change — only the EventBus implementation changes.
#
# For this lesson we use a pure in-memory bus.
# The interface (subscribe/publish) is identical to the Postgres-backed version.

class EventBus:
    """
    Simple synchronous in-memory event bus.

    In production this is backed by Postgres LISTEN/NOTIFY:
      - publish()  → INSERT INTO events ... + pg_notify(event.type, event.event_id)
      - subscribe() → LISTEN <event_type> in a background asyncpg connection

    The interface here is intentionally identical so the in-memory bus can
    be swapped for the Postgres bus in tests and production without changing
    any subscriber code.
    """

    def __init__(self) -> None:
        # Maps event_type string → list of handler callables
        self._subscribers: dict[str, list[Callable[[LexEvent], None]]] = {}
        # Audit log — in production this is the events table
        self._log: list[LexEvent] = []

    def subscribe(self, event_type: str, handler: Callable[[LexEvent], None]) -> None:
        """
        Register a handler for a specific event type.
        A single event type can have multiple subscribers — all fire.

        WHY no priority ordering?
        Subscribers must be idempotent and order-independent.
        If the audit logger depends on the notification handler running first,
        you have a design flaw — fix the subscriber, not the ordering.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def publish(self, event: LexEvent) -> None:
        """
        Emit an event.  All registered subscribers for event.type are called
        synchronously (in-memory version).

        In the Postgres version:
          INSERT INTO events (...) VALUES (...)
          NOTIFY <event_type>, <event_id>
        Subscribers in other processes receive the NOTIFY and handle the event.
        """
        self._log.append(event)
        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                # WHY: a broken handler must not crash the emitter.
                # In production, log to Sentry / error table.
                print(f"  [EventBus ERROR] handler={handler.__name__} "
                      f"event={event.type} error={exc}")

    def get_log(self, matter_id: Optional[str] = None) -> list[LexEvent]:
        """
        Return audit log, optionally filtered by matter.
        In production: SELECT * FROM events WHERE matter_id = $1 ORDER BY created_at
        """
        if matter_id:
            return [e for e in self._log if e.matter_id == matter_id]
        return list(self._log)

    def causation_chain(self, event_id: str) -> list[LexEvent]:
        """
        Walk backwards through causation_id links to reconstruct the event chain.
        Example: MORNING_BRIEF_READY ← DOCUMENT_PROCESSED ← NEW_DOCUMENT

        In production this is a recursive CTE on the events table:
          WITH RECURSIVE chain AS (
            SELECT * FROM events WHERE event_id = $1
            UNION ALL
            SELECT e.* FROM events e JOIN chain c ON e.event_id = c.causation_id
          ) SELECT * FROM chain ORDER BY created_at;
        """
        chain: list[LexEvent] = []
        lookup = {e.event_id: e for e in self._log}
        current_id: Optional[str] = event_id
        while current_id and current_id in lookup:
            event = lookup[current_id]
            chain.append(event)
            current_id = event.causation_id
        return chain


# ── SECTION 5: SUBSCRIBER EXAMPLES ───────────────────────────────────────────
#
# A subscriber is any callable that accepts a LexEvent and returns None.
# Subscribers must not raise exceptions (the bus catches them).
# Subscribers must be idempotent (the same event may be delivered more than
# once in the Postgres version if a worker restarts mid-delivery).

def limitation_handler(event: LexEvent) -> None:
    """
    Reacts to DOCUMENT_PROCESSED events.
    Checks if any extracted dates imply an approaching limitation deadline.
    In production: queries the facts table for dates, computes limitation,
    publishes LIMITATION_WARNING if threshold exceeded.
    """
    days_remaining = event.payload.get("limitation_days_remaining")
    if days_remaining is not None and days_remaining <= 30:
        print(f"  [LIMITATION HANDLER] ⚠  matter={event.matter_id} "
              f"limitation expires in {days_remaining} days — ALERT RAISED")
    else:
        print(f"  [LIMITATION HANDLER] matter={event.matter_id} "
              f"limitation check passed (days_remaining={days_remaining})")


def notification_handler(event: LexEvent) -> None:
    """
    Reacts to LIMITATION_WARNING and MORNING_BRIEF_READY events.
    Sends a Telegram/WhatsApp message to the assigned lawyer.
    In production: calls the Telegram bot API (or queues a notification job).
    """
    lawyer = event.payload.get("assigned_lawyer", "Advocate on Record")
    message = event.payload.get("message", f"Event: {event.type}")
    print(f"  [NOTIFICATION HANDLER] → Telegram to {lawyer}: \"{message}\"")


def audit_logger(event: LexEvent) -> None:
    """
    Reacts to ALL events.
    Writes a human-readable audit trail entry.
    In production: structured log entry → Loki/CloudWatch/Papertrail.
    WHY log everything? Bar Council rules require firms to maintain matter records.
    An event log is the finest-grained matter record available.
    """
    print(f"  [AUDIT LOG] {event.created_at[:19]}  "
          f"firm={event.firm_id}  matter={event.matter_id}  "
          f"actor={event.actor}  type={event.type}  "
          f"causation={event.causation_id or 'root'}")


# ── SECTION 6: LIVE DEMO ─────────────────────────────────────────────────────

def run_demo() -> None:
    print("=" * 60)
    print("DEMO: Event-Driven Runtime")
    print("=" * 60)

    bus = EventBus()
    FIRM = "firm_alpha"
    MATTER = "matter_ni138_001"

    # ── 6A: Subscribe handlers ──
    # limitation_handler listens for DOCUMENT_PROCESSED (to check dates)
    bus.subscribe("DOCUMENT_PROCESSED", limitation_handler)
    # notification_handler listens for warnings and briefs
    bus.subscribe("LIMITATION_WARNING", notification_handler)
    bus.subscribe("MORNING_BRIEF_READY", notification_handler)
    # audit_logger listens for every event type
    for event_type in EVENT_TYPES:
        bus.subscribe(event_type, audit_logger)

    print(f"\nSubscribers registered:")
    print(f"  DOCUMENT_PROCESSED  → limitation_handler, audit_logger")
    print(f"  LIMITATION_WARNING  → notification_handler, audit_logger")
    print(f"  MORNING_BRIEF_READY → notification_handler, audit_logger")
    print(f"  (all types)         → audit_logger")

    # ── 6B: Publish Event 1 — paralegal uploads bank records ──
    print(f"\n── Publishing: NEW_DOCUMENT ──")
    upload_event = LexEvent(
        firm_id=FIRM,
        matter_id=MATTER,
        actor="user",
        type="NEW_DOCUMENT",
        payload={
            "filename": "hdfc_bank_statement_jan_feb_2026.pdf",
            "pages": 47,
            "uploaded_by": "paralegal_priya",
        },
    )
    bus.publish(upload_event)

    # ── 6C: Publish Event 2 — background worker finishes processing ──
    # This event is caused by the upload event (causation_id links them).
    # The worker found that limitation expires in 12 days — within alert threshold.
    print(f"\n── Publishing: DOCUMENT_PROCESSED (caused by NEW_DOCUMENT) ──")
    processed_event = LexEvent(
        firm_id=FIRM,
        matter_id=MATTER,
        actor="agent",
        type="DOCUMENT_PROCESSED",
        payload={
            "document_id": upload_event.event_id,
            "facts_extracted": 8,
            "cheque_dates_found": 3,
            "limitation_days_remaining": 12,  # ← will trigger the limitation handler
        },
        causation_id=upload_event.event_id,  # ← tracing: this event was caused by upload
    )
    bus.publish(processed_event)

    # ── 6D: Publish Event 3 — morning brief ready ──
    print(f"\n── Publishing: MORNING_BRIEF_READY ──")
    brief_event = LexEvent(
        firm_id=FIRM,
        matter_id=MATTER,
        actor="system",
        type="MORNING_BRIEF_READY",
        payload={
            "brief_url": "https://lexagent.firm.internal/briefs/brief_20260531",
            "assigned_lawyer": "Adv. Kavita Sharma",
            "message": "Morning brief ready — NI Act 138 matter. "
                       "URGENT: Limitation in 12 days. 8 new facts extracted.",
            "headline_alerts": ["Limitation in 12 days", "3 cheque dates extracted"],
        },
        causation_id=processed_event.event_id,
    )
    bus.publish(brief_event)

    # ── 6E: Show the audit log ──
    print(f"\n── Full Audit Log for matter={MATTER} ──")
    for entry in bus.get_log(matter_id=MATTER):
        print(f"  [{entry.type}] event_id={entry.event_id} "
              f"actor={entry.actor} causation={entry.causation_id or 'root'}")

    # ── 6F: Show the causation chain starting from the brief ──
    print(f"\n── Causation Chain for MORNING_BRIEF_READY ──")
    print(f"  (Reading: 'was caused by' ←)")
    chain = bus.causation_chain(brief_event.event_id)
    for i, e in enumerate(chain):
        indent = "  " + ("← " * i)
        print(f"  {indent}[{e.type}] {e.event_id} (actor={e.actor})")

    print(f"\n{'=' * 60}")
    print("DEMO COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()


# ── PAUSE AND THINK ──────────────────────────────────────────────────────────
#
# 1. Open LEXAGENT_OS_V3_ARCHITECTURE_ROADMAP.md Section 8.
#    What Postgres mechanism does it propose for push-based event delivery
#    (so subscribers in other processes receive events without polling)?
#    How would you implement subscribe() using asyncpg's LISTEN command?
#
# 2. The audit_logger subscribes to all event types by looping over EVENT_TYPES.
#    This means adding a new event type does not automatically add an audit entry
#    unless the developer updates EVENT_TYPES.
#    Design a safer alternative: how would you ensure every published event is
#    always logged, regardless of whether it is in the catalogue?
#
# 3. causation_id allows tracing "MORNING_BRIEF_READY was caused by NEW_DOCUMENT".
#    Now imagine a LIMITATION_WARNING event was also caused by DOCUMENT_PROCESSED.
#    Draw the event graph for the full scenario in this demo.
#    Is it a chain (linear) or a DAG (branching)?  What does that imply for
#    the causation_chain() method above?
#
# 4. Look at lexagent/runtime/ in the repo.
#    Is there any event bus implementation there?
#    If not, what would you need to add to wire the EventBus into the existing
#    LangGraph graph so that node completions emit events?
#
# 5. The notification_handler sends a Telegram message.
#    Under DPDP (Digital Personal Data Protection Act, 2023), the firm must
#    be able to prove that no client personal data was included in automated
#    messages without consent.  What fields would you add to LexEvent.payload
#    to support a DPDP audit?  Where would the consent check live?
