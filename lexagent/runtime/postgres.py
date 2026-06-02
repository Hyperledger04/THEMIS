"""Postgres repository for the MVP agent runtime.

This module deliberately uses plain SQL and psycopg so the runtime stays small,
portable, and easy for a founder-led team to operate. Temporal/NATS/Kafka can
be introduced later without changing the public runtime models.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

from lexagent.runtime.models import AgentApproval, AgentJob, AgentRun, AgentStep


RUNTIME_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id       TEXT PRIMARY KEY,
    matter_id    TEXT NOT NULL,
    firm_id      TEXT NOT NULL DEFAULT 'default',
    user_id      TEXT NOT NULL DEFAULT 'default',
    goal         TEXT NOT NULL,
    status       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_jobs (
    job_id            TEXT PRIMARY KEY,
    matter_id          TEXT NOT NULL,
    run_id             TEXT NOT NULL REFERENCES agent_runs(run_id),
    type               TEXT NOT NULL,
    agent              TEXT NOT NULL,
    status             TEXT NOT NULL,
    requires_approval  BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    error               TEXT
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id      TEXT PRIMARY KEY,
    job_id       TEXT NOT NULL REFERENCES agent_jobs(job_id),
    run_id       TEXT NOT NULL REFERENCES agent_runs(run_id),
    name         TEXT NOT NULL,
    status       TEXT NOT NULL,
    input_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    step_id      TEXT NOT NULL REFERENCES agent_steps(step_id),
    run_id       TEXT NOT NULL REFERENCES agent_runs(run_id),
    tool_name    TEXT NOT NULL,
    input_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    status       TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_artifacts (
    artifact_id       TEXT PRIMARY KEY,
    matter_id         TEXT NOT NULL,
    run_id            TEXT NOT NULL REFERENCES agent_runs(run_id),
    job_id            TEXT,
    artifact_type     TEXT NOT NULL,
    title             TEXT NOT NULL,
    payload_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_approvals (
    approval_id      TEXT PRIMARY KEY,
    matter_id        TEXT NOT NULL,
    run_id           TEXT NOT NULL REFERENCES agent_runs(run_id),
    artifact_id      TEXT,
    requested_action TEXT NOT NULL,
    risk_level       TEXT NOT NULL,
    status           TEXT NOT NULL,
    approved_by      TEXT,
    approved_at      TIMESTAMPTZ,
    approval_notes   TEXT,
    created_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_notifications (
    notification_id TEXT PRIMARY KEY,
    matter_id       TEXT,
    run_id          TEXT,
    channel         TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    subject         TEXT,
    body            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'queued',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at         TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS source_anchors (
    anchor_id         TEXT PRIMARY KEY,
    matter_id          TEXT NOT NULL,
    document_id        TEXT NOT NULL,
    page               INTEGER,
    line_start         INTEGER,
    line_end           INTEGER,
    excerpt            TEXT NOT NULL,
    confidence         DOUBLE PRECISION NOT NULL DEFAULT 0,
    extractor_agent    TEXT,
    extraction_run_id  TEXT,
    created_at         TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_status ON agent_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_run ON agent_jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_source_anchors_document ON source_anchors(document_id, page);
"""


class PostgresRuntimeRepository:
    """Small repository for runtime persistence."""

    def __init__(self, postgres_url: str) -> None:
        self._postgres_url = postgres_url

    @contextmanager
    def _connect(self) -> Generator:
        import psycopg

        with psycopg.connect(self._postgres_url) as conn:
            yield conn

    def setup(self) -> None:
        """Create runtime tables if they do not exist."""
        with self._connect() as conn:
            conn.execute(RUNTIME_SCHEMA_SQL)
            conn.commit()

    def create_run(self, run: AgentRun) -> AgentRun:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_runs
                    (run_id, matter_id, firm_id, user_id, goal, status,
                     created_at, started_at, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run.run_id,
                    run.matter_id,
                    run.firm_id,
                    run.user_id,
                    run.goal,
                    run.status,
                    run.created_at,
                    run.started_at,
                    run.completed_at,
                ),
            )
            conn.commit()
        return run

    def create_job(self, job: AgentJob) -> AgentJob:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_jobs
                    (job_id, matter_id, run_id, type, agent, status,
                     requires_approval, payload_json, created_at,
                     started_at, completed_at, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    job.job_id,
                    job.matter_id,
                    job.run_id,
                    job.type,
                    job.agent,
                    job.status,
                    job.requires_approval,
                    json.dumps(job.payload),
                    job.created_at,
                    job.started_at,
                    job.completed_at,
                    job.error,
                ),
            )
            conn.commit()
        return job

    def record_step(self, step: AgentStep) -> AgentStep:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_steps
                    (step_id, job_id, run_id, name, status, input_json,
                     output_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    step.step_id,
                    step.job_id,
                    step.run_id,
                    step.name,
                    step.status,
                    json.dumps(step.input_json),
                    json.dumps(step.output_json),
                    step.created_at,
                ),
            )
            conn.commit()
        return step

    def pause_for_approval(self, approval: AgentApproval, job_id: Optional[str] = None) -> AgentApproval:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_approvals
                    (approval_id, matter_id, run_id, artifact_id, requested_action,
                     risk_level, status, approved_by, approved_at,
                     approval_notes, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    approval.approval_id,
                    approval.matter_id,
                    approval.run_id,
                    approval.artifact_id,
                    approval.requested_action,
                    approval.risk_level,
                    approval.status,
                    approval.approved_by,
                    approval.approved_at,
                    approval.approval_notes,
                    approval.created_at,
                ),
            )
            if job_id:
                conn.execute("UPDATE agent_jobs SET status='paused' WHERE job_id=%s", (job_id,))
            conn.commit()
        return approval

    def get_queued_jobs(self, limit: int = 10) -> list[AgentJob]:
        """Fetch the oldest queued jobs, ordered FIFO."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, matter_id, run_id, type, agent, status,
                       requires_approval, payload_json, created_at,
                       started_at, completed_at, error
                FROM agent_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            AgentJob(
                job_id=r[0], matter_id=r[1], run_id=r[2], type=r[3],
                agent=r[4], status=r[5], requires_approval=r[6],
                payload=r[7] or {}, created_at=str(r[8]),
                started_at=str(r[9]) if r[9] else None,
                completed_at=str(r[10]) if r[10] else None,
                error=r[11],
            )
            for r in rows
        ]

    def update_job_status(self, job_id: str, status: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            if status == "running":
                conn.execute(
                    "UPDATE agent_jobs SET status=%s, started_at=%s WHERE job_id=%s",
                    (status, now, job_id),
                )
            elif status in ("completed", "failed", "cancelled"):
                conn.execute(
                    "UPDATE agent_jobs SET status=%s, completed_at=%s WHERE job_id=%s",
                    (status, now, job_id),
                )
            else:
                conn.execute(
                    "UPDATE agent_jobs SET status=%s WHERE job_id=%s",
                    (status, job_id),
                )
            conn.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_jobs SET status='failed', completed_at=%s, error=%s WHERE job_id=%s",
                (now, error, job_id),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # F3: Runtime brake methods
    # ------------------------------------------------------------------

    def get_job_status(self, job_id: str) -> Optional[str]:
        """Return the current status string for a job, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM agent_jobs WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def cancel_job(self, job_id: str, reason: str) -> None:
        """Externally cancel a running or queued job (sets status='cancelled')."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE agent_jobs
                SET status = 'cancelled', completed_at = %s, error = %s
                WHERE job_id = %s
                """,
                (now, reason, job_id),
            )
            conn.commit()

    def update_job_activity(
        self,
        job_id: str,
        cost_usd_delta: float,
        phase: str,
    ) -> None:
        """
        Record a job heartbeat: bump last_activity_at, add cost, update phase.
        Called after each LLM step so HaltFlag's idle check stays accurate.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE agent_jobs
                SET last_activity_at = %s,
                    cost_usd = cost_usd + %s,
                    current_phase = %s
                WHERE job_id = %s
                """,
                (now, cost_usd_delta, phase, job_id),
            )
            conn.commit()

    def get_run_cost(self, run_id: str) -> float:
        """Sum cost_usd across all jobs for a run. Returns 0.0 if no jobs found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_jobs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return float(row[0]) if row else 0.0
