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
    parser: Literal["llamaparse", "pdfplumber", "docx", "ocr", "email", "unknown"] = "unknown"
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
