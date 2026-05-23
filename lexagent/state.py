# LANGGRAPH: State is a TypedDict that gets passed between every node in the graph.
# Think of it as the "file on the table" — each node reads it, adds to it, and passes it on.
# Nothing is stored inside the nodes themselves. Everything lives in state.
# When a node returns a dict, LangGraph merges only those keys into the existing state.
# You never return the full state — just the keys you changed.

from typing import Annotated, List, Optional, TypedDict

from langgraph.graph.message import add_messages

# LANGGRAPH: add_messages is a special reducer for the messages field.
# Instead of overwriting messages on each update, LangGraph appends new messages.
# This is how the agent keeps a full conversation history without manual list management.


class LexState(TypedDict):
    # --- Input ---
    user_input: str                           # Raw matter brief from the lawyer
    matter_id: Optional[str]                  # Unique ID for this matter (e.g. "M-20240501-001")

    # --- Intake (Phase 1) ---
    matter_type: Optional[str]                # e.g. "civil suit", "writ petition", "legal notice"
    parties: Optional[dict]                   # {"plaintiff": "ABC Ltd", "defendant": "XYZ Developers"}
    jurisdiction: Optional[str]               # Court + state/country (free-form, global scope)
    jurisdiction_country: Optional[str]       # Country code for skill selection (e.g. "IN", "US", "GB")
    purpose: Optional[str]                    # What document is needed and why
    key_clauses: Optional[List[str]]          # Specific reliefs, terms, or clauses required
    tone_preference: Optional[str]            # "senior formal" | "plain commercial" | etc.
    risks_to_address: Optional[List[str]]     # Known risks or sensitivities the lawyer flagged
    citations_required: Optional[bool]        # Does the lawyer want case law citations?
    intake_complete: bool                     # Gate: True when all required fields are filled
    clarifying_questions: Optional[List[str]] # Questions generated for the lawyer (legacy plain text)
    # Phase 8: structured question objects for Telegram inline keyboard rendering
    # Each object: {field, question, type: binary|mcq|open, options?: list[str]}
    pending_questions: Optional[List[dict]]
    active_skill_name: Optional[str]          # Human-readable loaded skill name (e.g. "Civil Litigation")
    # Intake fields collected via deep question banks (Phase 8)
    fundamental_right: Optional[str]
    article_invoked: Optional[str]
    cause_of_action_date: Optional[str]       # ISO date or free-text
    relief_sought: Optional[str]
    alternative_remedy: Optional[str]
    urgency: Optional[str]
    previous_orders: Optional[str]
    plaint_valuation: Optional[str]
    limitation_applicable: Optional[str]
    notice_period: Optional[str]
    bail_type: Optional[str]
    offence_section: Optional[str]
    custody_duration: Optional[str]

    # --- Research (Phase 4) ---
    research_findings: Optional[List[dict]]   # [{case_name, citation, relevance, url, source}]
    statutes_cited: Optional[List[str]]       # ["CPC O.XXXIX R.1&2", "Specific Relief Act S.38"]
    limitation_analysis: Optional[str]        # Limitation period check result (Phase 4)

    # --- Draft (Phase 1+) ---
    document_outline: Optional[str]           # Structural outline (generated before full draft)
    draft_output: Optional[str]               # Full draft text
    risk_annotations: Optional[List[dict]]    # [{clause, risk_level: H|M|L, note}] (Phase 5)
    plain_english_summary: Optional[str]      # 2-3 line client summary

    # --- Citation Verification (Phase 4) ---
    citations_verified: bool                  # True once cite node has run
    unverified_citations: Optional[List[str]] # Citations flagged for human review

    # --- RAG Retrieval (Phase 5) ---
    retrieval_chunks: Optional[List[dict]]    # Raw (child, parent) chunk pairs from hybrid retriever
    grounded_citations: Optional[List[dict]]  # [{chunk_id, source, paragraph_ref, verified}]
    docx_path: Optional[str]                  # Path to generated .docx file (set by review node)

    # --- Phase 6: RAGFlow Features ---
    raptor_tree: Optional[List[dict]]         # RAPTOR summary hierarchy [{layer, text, source_chunks}]
    entity_graph: Optional[dict]              # GraphRAG entity graph for this matter

    # --- Phase 7: Routing + Contract Review ---
    workflow_mode: Optional[str]              # "draft" (default) | "contract_review"
    contract_upload_path: Optional[str]       # Path to uploaded PDF for contract review
    contract_risk_analysis: Optional[dict]    # Structured risk findings from contract_review node
    contract_review_output: Optional[str]     # Formatted markdown risk report

    # --- Phase 8 (Roadmap): Hearing + Deadline Intelligence ---
    # litigation_stage tracks where a criminal matter stands in the procedural timeline.
    # WHY: stage determines which documents to draft next (e.g., bail at FIR stage vs revision
    # at trial stage) and which court fee schedule applies.
    litigation_stage: Optional[str]           # "fir" | "charge_sheet" | "cognizance" | "trial" | "appeal"
    hearing_date: Optional[str]               # Next scheduled hearing date (ISO or free-text)

    # --- Phase 8 (UX): Agentic routing + post-draft actions ---
    # WHY: approved_tools lets user select which research sources to use before research runs.
    # None = not yet decided (show routing menu); empty list = user chose skip.
    approved_tools: Optional[List[str]]
    pending_action: Optional[str]             # Post-draft action selected by lawyer

    # --- Conversation history ---
    # LANGGRAPH: Annotated[List, add_messages] tells LangGraph to use the add_messages
    # reducer instead of overwriting. Every time a node adds to messages, LangGraph
    # appends — so the full conversation history is always preserved here.
    messages: Annotated[List, add_messages]

    # --- Meta ---
    lawyer_soul: Optional[dict]               # Loaded from ~/.lexagent/SOUL.md (Phase 2)
    active_skill: Optional[str]               # Which skill.md content is active (Phase 3)
    error: Optional[str]                      # Any error — nodes catch and set this, never raise
    next_node: Optional[str]                  # For explicit routing decisions
    # Phase 8: telegram user_id stored in state so nodes can be traced back to a session
    telegram_user_id: Optional[int]

    # --- Phase 9: Multi-Tenant Identity ---
    # WHY: Every matter belongs to a firm and a lawyer. These three fields let
    # the control plane route the right SOUL.md, Qdrant collection, and Postgres
    # rows without ambiguity across tenants.
    firm_id: Optional[str]                    # Tenant identifier (e.g. "firm_sharma_associates")
    user_id: Optional[str]                    # Lawyer identifier within the firm
    # Preferred delivery gateway for proactive notifications (cron results, reminders)
    preferred_gateway: Optional[str]          # "telegram" | "whatsapp" | "slack" | "web"
    # Phase 9: background task type when agent runs on a cron/queue
    background_task: Optional[str]            # "morning_brief" | "deadline_scan" | "research_queue"

    # --- Phase 9B: Voice AI Gateway ---
    # WHY: voice_session_id lets the voice gateway look up the matching
    # VoiceSession (and its TTS/STT context) from the LangGraph state,
    # so mid-graph questions can be spoken back to the right caller.
    voice_session_id: Optional[str]           # Twilio Call SID or WebSocket UUID
    voice_channel: Optional[str]              # "twilio" | "websocket"
