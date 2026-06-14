"""Typed Matter Workspace models.

These models are intentionally provider- and storage-agnostic. Postgres stores
them, the runtime creates them, and every UI can render them without knowing
which agent or model produced the object.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    """Create stable human-readable IDs such as matter_xxx or anchor_xxx."""
    return f"{prefix}_{uuid4().hex}"


class Matter(BaseModel):
    matter_id: str = Field(default_factory=lambda: new_id("matter"))
    firm_id: str = "default"
    user_id: str = "default"
    title: str
    matter_type: str
    jurisdiction: Optional[str] = None
    status: Literal["active", "paused", "closed", "archived"] = "active"
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class DocumentRecord(BaseModel):
    document_id: str = Field(default_factory=lambda: new_id("doc"))
    matter_id: str
    firm_id: str = "default"
    filename: str
    mime_type: Optional[str] = None
    storage_uri: str
    parser: Literal["llamaparse", "pdfplumber", "docx", "ocr", "email", "plaintext", "unknown"] = "unknown"
    page_count: Optional[int] = None
    status: Literal["uploaded", "processing", "indexed", "failed"] = "uploaded"
    created_at: str = Field(default_factory=_now_iso)


class SourceAnchor(BaseModel):
    """Clickable source footnote anchored to page + extracted line."""

    anchor_id: str = Field(default_factory=lambda: new_id("anchor"))
    matter_id: str
    document_id: str
    page: Optional[int] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    excerpt: str
    confidence: float = 0.0
    extractor_agent: Optional[str] = None
    extraction_run_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)

    def viewer_url(self) -> str:
        """Return the web viewer URL used by footnotes and approval screens."""
        page = "" if self.page is None else str(self.page)
        line = "" if self.line_start is None else str(self.line_start)
        return (
            f"/document-viewer/{self.matter_id}/{self.document_id}"
            f"?page={page}&line={line}&anchor={self.anchor_id}"
        )

    def footnote(self) -> str:
        """Return the inline footnote marker, e.g. [F3] or [anchor_xxx]."""
        return f"[{self.anchor_id}]"


class ExtractedFact(BaseModel):
    fact_id: str = Field(default_factory=lambda: new_id("fact"))
    matter_id: str
    text: str
    status: Literal["extracted", "confirmed", "disputed", "needs_source"] = "extracted"
    confidence: float = 0.0
    source_anchor_ids: list[str] = Field(default_factory=list)
    extractor_agent: Optional[str] = None
    extraction_run_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)

    def footnoted_text(self) -> str:
        suffix = "".join(f"[{anchor_id}]" for anchor_id in self.source_anchor_ids)
        return f"{self.text} {suffix}".strip()


class ChronologyItem(BaseModel):
    chronology_id: str = Field(default_factory=lambda: new_id("chrono"))
    matter_id: str
    date_text: str
    event: str
    normalized_date: Optional[str] = None
    confidence: float = 0.0
    source_anchor_ids: list[str] = Field(default_factory=list)
    extractor_agent: Optional[str] = None
    extraction_run_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class EvidenceItem(BaseModel):
    evidence_id: str = Field(default_factory=lambda: new_id("evidence"))
    matter_id: str
    title: str
    description: str
    document_id: Optional[str] = None
    source_anchor_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    created_at: str = Field(default_factory=_now_iso)


class Party(BaseModel):
    party_id: str = Field(default_factory=lambda: new_id("party"))
    matter_id: str
    name: str
    role: Literal["complainant", "respondent", "applicant", "opponent", "witness", "other"] = "other"
    address: Optional[str] = None
    contact: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class Issue(BaseModel):
    issue_id: str = Field(default_factory=lambda: new_id("issue"))
    matter_id: str
    text: str
    category: Optional[str] = None
    status: Literal["open", "resolved", "dropped"] = "open"
    source_anchor_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


class Authority(BaseModel):
    authority_id: str = Field(default_factory=lambda: new_id("auth"))
    matter_id: str
    authority_type: Literal["case", "statute", "regulation", "circular", "order"] = "case"
    title: str
    citation: Optional[str] = None
    court: Optional[str] = None
    url: Optional[str] = None
    proposition: str
    treatment: Literal["binding", "persuasive", "distinguished", "overruled", "unknown"] = "unknown"
    # §11A Failure Mode 2 — Jurisdictional Conflation: every authority must carry
    # its provenance so retrieval and drafting nodes can separate binding SC opinions
    # from persuasive foreign cases before they reach any prompt.
    jurisdiction: str = "india"
    country: str = "india"
    court_tier: Literal[
        "binding_sc", "binding_hc", "persuasive_domestic", "persuasive_foreign", "academic"
    ] = "persuasive_domestic"
    corpus_namespace: str = "corpus:india_sc"
    # §11A Failure Mode 1 — Citation Drift: verification must check the ratio
    # paragraph, not just that the case exists. tri-state prevents false confidence.
    verified_excerpt: Optional[str] = None
    paragraph_number: Optional[str] = None
    verification_status: Literal["verified", "partial", "contradicted", "unverified"] = "unverified"
    verified: bool = False
    source_anchor_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


class Draft(BaseModel):
    draft_id: str = Field(default_factory=lambda: new_id("draft"))
    matter_id: str
    doc_type: str
    version: int = 1
    content: str
    status: Literal["draft", "under_review", "approved", "filed"] = "draft"
    verification_report_id: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class FeedbackItem(BaseModel):
    feedback_id: str = Field(default_factory=lambda: new_id("feedback"))
    matter_id: Optional[str] = None
    user_id: str
    target_type: Literal["draft", "research", "authority", "risk", "skill", "checklist"]
    target_id: Optional[str] = None
    signal: Literal["accepted", "rejected", "edited", "preferred", "corrected"]
    note: Optional[str] = None
    diff: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class Deadline(BaseModel):
    deadline_id: str = Field(default_factory=lambda: new_id("deadline"))
    matter_id: str
    title: str
    due_date: str
    deadline_type: Literal["limitation", "filing", "hearing", "notice", "other"] = "other"
    status: Literal["upcoming", "overdue", "completed", "waived"] = "upcoming"
    source_anchor_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    matter_id: str
    title: str
    status: Literal["pending", "in_progress", "completed", "cancelled"] = "pending"
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class ResearchMemo(BaseModel):
    """First-class workspace object for research memos produced by living-agent jobs."""

    memo_id: str = Field(default_factory=lambda: new_id("memo"))
    matter_id: str
    title: str
    content: str
    query: Optional[str] = None
    authority_ids: list[str] = Field(default_factory=list)
    source_anchor_ids: list[str] = Field(default_factory=list)
    agent_run_id: Optional[str] = None
    status: Literal["draft", "reviewed", "archived"] = "draft"
    created_at: str = Field(default_factory=_now_iso)


class RiskAnalysis(BaseModel):
    """Adversarial risk analysis attached to a matter or a specific draft."""

    risk_id: str = Field(default_factory=lambda: new_id("risk"))
    matter_id: str
    draft_id: Optional[str] = None
    title: str
    summary: str
    risks: list[dict] = Field(default_factory=list)
    agent_run_id: Optional[str] = None
    status: Literal["draft", "reviewed", "archived"] = "draft"
    created_at: str = Field(default_factory=_now_iso)


class StylePreference(BaseModel):
    """Per-lawyer or per-firm drafting preference extracted from accepted feedback.

    Injected into drafting prompts so the agent learns from accepted edits over time.
    Suggestions only — core prompts are never silently rewritten (§8C Learning Loop rule).
    """

    preference_id: str = Field(default_factory=lambda: new_id("pref"))
    user_id: str
    firm_id: str = "default"
    matter_type: Optional[str] = None
    doc_type: Optional[str] = None
    preference_text: str
    source_feedback_ids: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class PlaybookNote(BaseModel):
    """Matter-type and court-specific observation captured from lawyer feedback.

    Used by the planner and drafting nodes to adapt to jurisdiction/forum patterns.
    Never silently overwrites skill files — surfaced as suggestions first.
    """

    note_id: str = Field(default_factory=lambda: new_id("pnote"))
    firm_id: str = "default"
    matter_type: Optional[str] = None
    jurisdiction: Optional[str] = None
    court: Optional[str] = None
    observation: str
    source_feedback_ids: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: str = Field(default_factory=_now_iso)
