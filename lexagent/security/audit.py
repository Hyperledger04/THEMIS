"""
DPDP-compliant audit logger.

WHY: Indian legal matters carry client confidentiality obligations (BCI rules)
and, for firms with digital data, DPDP Act 2023 obligations. Every access,
generation, and deletion event must be logged with a 7-year retention window.

Design choices:
- Non-blocking: log_action() catches and swallows all exceptions so an audit
  log failure NEVER propagates to the request handler. Audit is best-effort
  so it never breaks the application.
- Append-only: the audit_log table has no UPDATE or DELETE path in this
  module. Records are only purged via the scheduled purge_old_audit_entries()
  job after the retention window expires.
- Schema version: every row carries schema_version so we can evolve the table
  structure without breaking historical records.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


_SCHEMA_VERSION = 3


class AuditAction:
    """Canonical audit action strings — import these instead of bare strings."""
    # Auth
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_ISSUED = "auth.token_issued"
    AUTH_TOKEN_REVOKED = "auth.token_revoked"
    # Matter / draft lifecycle
    MATTER_CREATED = "matter.created"
    MATTER_ACCESSED = "matter.accessed"
    DRAFT_GENERATED = "draft.generated"
    DOCUMENT_UPLOADED = "document.uploaded"
    RESEARCH_RUN = "research.run"
    # Inference privacy tier
    INFERENCE_ROUTED = "inference.routed"
    INFERENCE_TIER_VIOLATION = "inference.tier_violation"
    # PII anonymization
    PII_ANONYMIZED = "pii.anonymized"
    PII_RESTORED = "pii.restored"
    # Runtime brakes
    JOB_COST_CAP = "job.cost_cap"
    JOB_HALTED = "job.halted"
    JOB_PHASE_VIOLATION = "job.phase_violation"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,
    firm_id        TEXT,
    user_id        TEXT,
    action         TEXT    NOT NULL,
    resource_type  TEXT,
    resource_id    TEXT,
    ip             TEXT,
    user_agent     TEXT,
    detail_json    TEXT,
    schema_version INTEGER NOT NULL DEFAULT 3
);
CREATE INDEX IF NOT EXISTS idx_audit_ts   ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(firm_id, user_id);
CREATE INDEX IF NOT EXISTS idx_audit_act  ON audit_log(action);
"""


def _get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_CREATE_TABLE)
    conn.commit()
    return conn


def log_action(
    action: str,
    *,
    firm_id: Optional[str] = None,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    detail: Optional[dict] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    Append one audit entry. Never raises — all errors are silently swallowed.

    WHY non-blocking silent failure: audit logging is observability
    infrastructure. A disk-full error or locked DB must never cause a
    lawyer's draft to fail. Log, don't block.

    Instrumentation points (from Enterprise 10x10 plan):
      matter.accessed, draft.generated, document.uploaded, research.run,
      auth.login, auth.logout, auth.token_issued, auth.token_revoked,
      key.rotated, user.created, user.deleted, matter.created
    """
    try:
        if db_path is None:
            from lexagent.config import LexConfig
            db_path = str(Path(LexConfig().sessions_db).expanduser())

        conn = _get_db(db_path)
        conn.execute(
            """
            INSERT INTO audit_log
              (timestamp, firm_id, user_id, action, resource_type,
               resource_id, ip, user_agent, detail_json, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(tz=timezone.utc).isoformat(),
                firm_id,
                user_id,
                action,
                resource_type,
                resource_id,
                ip,
                user_agent,
                json.dumps(detail) if detail else None,
                _SCHEMA_VERSION,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # WHY: audit must never crash the application


def purge_old_audit_entries(
    retain_days: int = 2555,  # 7 years — Indian legal compliance default
    db_path: Optional[str] = None,
) -> int:
    """
    Delete audit entries older than retain_days. Returns rows deleted.

    Called by the APScheduler cron engine once a week.
    retain_days=2555 = 7 years (365.25 * 7).
    """
    try:
        if db_path is None:
            from lexagent.config import LexConfig
            db_path = str(Path(LexConfig().sessions_db).expanduser())

        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=retain_days)).isoformat()
        conn = _get_db(db_path)
        cursor = conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception:
        return 0
