"""
Pydantic models for the Playbook DAG execution pipeline.

Field names deliberately mirror the YAML keys in lexagent/contract/defaults/nda.yaml
so PlaybookSpec can be constructed directly from yaml.safe_load() output.

WHY Pydantic instead of plain dicts:
  - Type-safe access catches YAML field typos at load time, not at review time.
  - Validators coerce optional fields (notes, rationale) cleanly.
  - PlaybookExecutor can pass typed models to functions without isinstance checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Playbook structure (mirrors YAML schema)
# ---------------------------------------------------------------------------

class PlaybookPosition(BaseModel):
    """One negotiating position — a single clause entry in a playbook."""
    clause: str
    our_position: str
    rationale: Optional[str] = None
    precedents: list[str] = Field(default_factory=list)


class PlaybookSpec(BaseModel):
    """
    A complete firm playbook. Constructed from YAML via load_playbook_spec().

    All fields except id/name/contract_type/positions are optional so minimal
    YAML files (like test fixtures) construct without errors.
    """
    id: str
    name: str
    contract_type: str
    positions: list[PlaybookPosition] = Field(default_factory=list)
    notes: Optional[str] = None
    created: Optional[str] = None
    source: Optional[str] = None  # "bundled" | "custom"

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookSpec":
        """Construct from raw YAML dict. Coerces positions from list-of-dicts."""
        positions_raw = data.get("positions", [])
        positions = [
            p if isinstance(p, PlaybookPosition) else PlaybookPosition(**p)
            for p in positions_raw
        ]
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            contract_type=data.get("contract_type", ""),
            positions=positions,
            notes=data.get("notes"),
            created=str(data["created"]) if data.get("created") else None,
            source=data.get("source"),
        )


# ---------------------------------------------------------------------------
# Execution tracking models
# ---------------------------------------------------------------------------

class PositionResult(BaseModel):
    """Result of evaluating one PlaybookPosition against the contract text."""
    clause: str
    our_position: str
    detected: bool
    deviation: Optional[str] = None    # Description if contract deviates from our position
    severity: Literal["ok", "minor", "major", "critical"] = "ok"
    excerpt: Optional[str] = None      # Relevant contract excerpt


class PlaybookExecution(BaseModel):
    """Tracks one end-to-end playbook review run against a contract."""
    execution_id: str = Field(default_factory=lambda: f"pb_exec_{uuid4().hex}")
    playbook_id: str
    matter_id: Optional[str] = None
    document_path: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    results: list[PositionResult] = Field(default_factory=list)
    overall_risk: Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"] = "UNKNOWN"
    created_at: str = Field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    error: Optional[str] = None

    def summary(self) -> dict:
        """Return a compact summary dict for storage and CLI display."""
        return {
            "execution_id": self.execution_id,
            "playbook_id": self.playbook_id,
            "overall_risk": self.overall_risk,
            "positions_checked": len(self.results),
            "deviations": sum(1 for r in self.results if r.deviation),
            "critical": sum(1 for r in self.results if r.severity == "critical"),
            "major": sum(1 for r in self.results if r.severity == "major"),
        }
