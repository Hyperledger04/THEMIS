# LANGGRAPH: State is a TypedDict that gets passed between every node in the graph.
# Think of it as the "file on the table" — each node reads it, adds to it, and passes it on.
# Nothing is stored inside the nodes themselves. Everything lives in state.
# When a node returns a dict, LangGraph merges only those keys into the existing state.
# You never return the full state — just the keys you changed.
#
# V3.2 — State Split:
#   - SeniorCounselState replaces the old flat LexState (all existing fields preserved).
#   - Four child TypedDicts scope state per specialist subgraph (used from V3.3 onward).
#   - LexState alias kept at the bottom for backward compatibility; remove in V3.3 cleanup.

from typing import List, Optional, TypedDict


class SeniorCounselState(TypedDict):
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
    # S.138 NI Act specific — drives S.141 conditional block in draft node
    accused_entity_type: Optional[str]  # "individual" | "proprietorship" | "partnership" | "company"
    notice_date: Optional[str]          # Date legal notice was sent (ISO or free-text)
    cheque_amount: Optional[str]        # Cheque amount in figures (drives prayer_fine_amount)

    # --- Exhibit registry (Phase: court-ready drafts) ---
    # WHY: Built during intake before any LLM call so that complaint body,
    # affidavit, and list-of-documents all share the same exhibit labels.
    # {"invoice": "EX-CW1/A", "cheque": "EX-CW1/B", ...}
    exhibit_registry: Optional[dict]

    # --- Affidavit sub-document (Phase: court-ready drafts) ---
    affidavit_output: Optional[str]     # Full affidavit text (12-14 first-person paragraphs)
    affidavit_path: Optional[str]       # Path to affidavit_evidence.docx

    # --- Research (Phase 4) ---
    research_only: Optional[bool]             # If True, graph stops after research node (no draft)
    research_findings: Optional[List[dict]]   # [{case_name, citation, relevance, url, source}]
    statutes_cited: Optional[List[str]]       # ["CPC O.XXXIX R.1&2", "Specific Relief Act S.38"]
    limitation_analysis: Optional[str]        # Limitation period check result (Phase 4)

    # --- ReAct Research + Citation Gate (Phase R1) ---
    citation_gate_dropped: Optional[List[dict]]  # Findings dropped by the enforcement gate
    research_agent_trace: Optional[List[dict]]   # [{step, tool, input, output, timestamp}]
    research_tool_toggles: Optional[dict]        # {kanoon: bool, tavily: bool, ecourts: bool}

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
    workflow_mode: Optional[str]              # "draft" (default) | "contract_review" | "contract_draft"
    contract_upload_path: Optional[str]       # Path to uploaded PDF for contract review
    contract_risk_analysis: Optional[dict]    # Structured risk findings from contract_review node
    contract_review_output: Optional[str]     # Formatted markdown risk report
    contract_lifecycle: Optional[str]         # "draft"|"under_review"|"redlines_sent"|"executed"|"expired"
    active_playbook: Optional[str]            # Playbook ID loaded for this contract matter

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
    # Plain list of OpenAI-format message dicts: {"role": "user"|"assistant"|"system", "content": "..."}
    # WHY: Using plain dicts instead of LangChain HumanMessage/AIMessage objects removes the
    # langchain-core dependency and works directly with litellm.acompletion() without conversion.
    # Nodes that add messages must explicitly append:
    #   return {"messages": state.get("messages", []) + [{"role": "assistant", "content": text}]}
    messages: List[dict]

    # --- Meta ---
    lawyer_soul: Optional[dict]               # Loaded from ~/.themis/SOUL.md (Phase 2)
    active_skill: Optional[str]               # Which skill.md content is active (Phase 3)

    # Dynamic skill router (Phase: dynamic-skill-router)
    # forced_skill_names: set by --skill CLI flag or /skill Telegram command before graph runs.
    # selected_skill_names: names actually loaded by skill_router node (audit/debug).
    forced_skill_names: Optional[List[str]]
    selected_skill_names: Optional[List[str]]
    active_agent: Optional[dict]              # Loaded agent persona (from lex agent system or @mention)
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

    # --- Redline (doc-haus Feature 1) ---
    redline_source_path: Optional[str]   # original .docx to diff against
    redline_output_path: Optional[str]   # path written by review node

    # --- V3.3: Senior Counsel coordination ---
    # WHY: execution_plan drives the coordinate → send() loop. Each entry is popped
    # after the specialist completes, so coordinate always looks at plan[0] for next.
    execution_plan:      Optional[List[dict]]   # [{"specialist": "researcher", "params": {}}]
    active_specialist:   Optional[str]           # specialist currently being dispatched
    # WHY: status mirrors the Postgres matter_status enum so persist_matter() can sync.
    status:              Optional[str]           # matter workflow status
    # Handoff slots — Senior Counsel reads these after each specialist completes.
    review_result:       Optional[dict]          # {passed: bool, issues: [...], risk_score: float}
    verification_result: Optional[dict]          # {verified: [...], failed: [...], confidence: {}}

    # --- Chamber review (doc-haus Feature 2) ---
    chamber_enabled: Optional[bool]      # activated by --chamber flag or contract_review
    chamber_issues: Optional[str]        # Reviewer LLM output
    chamber_pushback: Optional[str]      # Challenger LLM output
    chamber_review: Optional[str]        # Summarizer final review

    # --- Grid analysis (doc-haus Feature 3) ---
    grid_questions: Optional[List[str]]  # questions to run across all matter docs
    grid_results: Optional[dict]         # {question: {doc_name: answer}}


# ---------------------------------------------------------------------------
# V3.2 — Specialist child TypedDicts (used by subgraphs from V3.3 onward)
# Each specialist receives only the fields it needs; it never reads the full
# SeniorCounselState.  Senior Counsel copies relevant keys in before dispatch
# and merges handoff slots back after the subgraph completes.
# ---------------------------------------------------------------------------

class ResearcherState(TypedDict):
    matter_id:            str
    matter_type:          Optional[str]
    jurisdiction:         Optional[str]
    parties:              Optional[dict]
    purpose:              Optional[str]
    search_queries:       List[str]
    tool_calls_log:       List[dict]
    research_findings:    List[dict]   # [{title, citation, doc_excerpt, url, verified: bool}]
    statutes_cited:       List[str]
    limitation_analysis:  Optional[str]
    thread_messages:      List[dict]   # internal audit trail — never shown to lawyer


class DrafterState(TypedDict):
    matter_id:              str
    matter_type:            Optional[str]
    jurisdiction:           Optional[str]
    parties:                Optional[dict]
    research_findings:      List[dict]
    lawyer_soul:            Optional[str]
    active_skill:           Optional[str]
    draft_output:           Optional[str]
    plain_english_summary:  Optional[str]
    risk_annotations:       List[dict]
    thread_messages:        List[dict]


class ReviewerState(TypedDict):
    matter_id:              str
    draft_output:           str
    research_findings:      List[dict]
    matter_type:            Optional[str]
    review_result:          dict         # {passed: bool, issues: [...], risk_score: float}
    unverified_citations:   List[dict]
    citations_verified:     bool
    thread_messages:        List[dict]


class VerificationState(TypedDict):
    matter_id:              str
    unverified_citations:   List[dict]   # [{title, citation, doc_excerpt, url}]
    lawyer_approved:        bool
    verification_result:    dict         # {verified: [...], failed: [...], confidence: {}}
    thread_messages:        List[dict]


# ---------------------------------------------------------------------------
# Backward-compat alias — all existing nodes and tests import LexState;
# they resolve to SeniorCounselState transparently.
# WHY: removing this alias is a V3.3 cleanup task, not V3.2 scope.
# ---------------------------------------------------------------------------
LexState = SeniorCounselState
