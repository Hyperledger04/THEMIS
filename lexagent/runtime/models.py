"""Provider-agnostic agent runtime models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def runtime_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


AgentKind = Literal[
    "document_processing_agent",
    "chronology_agent",
    "evidence_agent",
    "ni_act_compliance_agent",
    "research_agent",
    "risk_agent",
    "drafting_agent",
    "verification_agent",
    "notification_agent",
    "learning_agent",
]

JobStatus = Literal["queued", "running", "paused", "completed", "failed", "cancelled"]


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: runtime_id("run"))
    matter_id: str
    firm_id: str = "default"
    user_id: str = "default"
    goal: str
    status: JobStatus = "queued"
    created_at: str = Field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class AgentJob(BaseModel):
    job_id: str = Field(default_factory=lambda: runtime_id("job"))
    matter_id: str
    run_id: str
    type: str
    agent: AgentKind
    status: JobStatus = "queued"
    requires_approval: bool = False
    payload: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class AgentStep(BaseModel):
    step_id: str = Field(default_factory=lambda: runtime_id("step"))
    job_id: str
    run_id: str
    name: str
    status: JobStatus = "queued"
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)


class AgentToolCall(BaseModel):
    tool_call_id: str = Field(default_factory=lambda: runtime_id("tool"))
    step_id: str
    run_id: str
    tool_name: str
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    status: JobStatus = "queued"
    created_at: str = Field(default_factory=_now_iso)


class AgentArtifact(BaseModel):
    artifact_id: str = Field(default_factory=lambda: runtime_id("artifact"))
    matter_id: str
    run_id: str
    job_id: Optional[str] = None
    artifact_type: str
    title: str
    payload: dict = Field(default_factory=dict)
    source_anchor_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


class AgentApproval(BaseModel):
    approval_id: str = Field(default_factory=lambda: runtime_id("approval"))
    matter_id: str
    run_id: str
    artifact_id: Optional[str] = None
    requested_action: str
    risk_level: Literal["low", "medium", "high"] = "medium"
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    approval_notes: Optional[str] = None
    created_at: str = Field(default_factory=_now_iso)


class AgentNotification(BaseModel):
    notification_id: str = Field(default_factory=lambda: runtime_id("notif"))
    matter_id: Optional[str] = None
    run_id: Optional[str] = None
    channel: Literal["telegram", "email", "webhook", "console"] = "console"
    recipient: str
    subject: Optional[str] = None
    body: str
    status: Literal["queued", "sent", "failed"] = "queued"
    created_at: str = Field(default_factory=_now_iso)
    sent_at: Optional[str] = None


class RuntimeEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: runtime_id("event"))
    matter_id: Optional[str] = None
    run_id: Optional[str] = None
    event_type: str
    payload: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
