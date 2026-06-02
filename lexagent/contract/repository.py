"""
Postgres repository for playbook execution records.

Uses the same plain psycopg pattern as lexagent/runtime/postgres.py — no ORM,
no query builder, just parameterised SQL so the schema stays auditable.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

from lexagent.contract.models import PlaybookExecution, PositionResult


class PlaybookRepository:
    """Persists PlaybookExecution records to Postgres."""

    def __init__(self, postgres_url: str) -> None:
        self._postgres_url = postgres_url

    @contextmanager
    def _connect(self) -> Generator:
        import psycopg
        with psycopg.connect(self._postgres_url) as conn:
            yield conn

    def setup(self) -> None:
        """Create the playbook_executions table if it does not exist."""
        with self._connect() as conn:
            conn.execute(_SCHEMA_SQL)
            conn.commit()

    def create_execution(self, execution: PlaybookExecution) -> PlaybookExecution:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO playbook_executions
                    (execution_id, playbook_id, matter_id, document_path,
                     status, results_json, overall_risk, created_at,
                     completed_at, error)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
                """,
                (
                    execution.execution_id,
                    execution.playbook_id,
                    execution.matter_id,
                    execution.document_path,
                    execution.status,
                    json.dumps([r.model_dump() for r in execution.results]),
                    execution.overall_risk,
                    execution.created_at,
                    execution.completed_at,
                    execution.error,
                ),
            )
            conn.commit()
        return execution

    def update_execution(self, execution: PlaybookExecution) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE playbook_executions
                SET status = %s,
                    results_json = %s::jsonb,
                    overall_risk = %s,
                    completed_at = %s,
                    error = %s
                WHERE execution_id = %s
                """,
                (
                    execution.status,
                    json.dumps([r.model_dump() for r in execution.results]),
                    execution.overall_risk,
                    now,
                    execution.error,
                    execution.execution_id,
                ),
            )
            conn.commit()

    def get_execution(self, execution_id: str) -> Optional[PlaybookExecution]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT execution_id, playbook_id, matter_id, document_path,
                       status, results_json, overall_risk, created_at,
                       completed_at, error
                FROM playbook_executions
                WHERE execution_id = %s
                """,
                (execution_id,),
            ).fetchone()
        if not row:
            return None
        results_raw = row[5] or []
        return PlaybookExecution(
            execution_id=row[0],
            playbook_id=row[1],
            matter_id=row[2],
            document_path=row[3],
            status=row[4],
            results=[PositionResult(**r) for r in results_raw],
            overall_risk=row[6],
            created_at=str(row[7]),
            completed_at=str(row[8]) if row[8] else None,
            error=row[9],
        )

    def list_executions(self, matter_id: str) -> list[PlaybookExecution]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT execution_id, playbook_id, matter_id, document_path,
                       status, results_json, overall_risk, created_at,
                       completed_at, error
                FROM playbook_executions
                WHERE matter_id = %s
                ORDER BY created_at DESC
                """,
                (matter_id,),
            ).fetchall()
        return [
            PlaybookExecution(
                execution_id=r[0], playbook_id=r[1], matter_id=r[2],
                document_path=r[3], status=r[4],
                results=[PositionResult(**x) for x in (r[5] or [])],
                overall_risk=r[6], created_at=str(r[7]),
                completed_at=str(r[8]) if r[8] else None, error=r[9],
            )
            for r in rows
        ]


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS playbook_executions (
    execution_id  TEXT PRIMARY KEY,
    playbook_id   TEXT NOT NULL,
    matter_id     TEXT,
    document_path TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    results_json  JSONB NOT NULL DEFAULT '[]'::jsonb,
    overall_risk  TEXT NOT NULL DEFAULT 'UNKNOWN',
    created_at    TIMESTAMPTZ NOT NULL,
    completed_at  TIMESTAMPTZ,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_pb_exec_matter ON playbook_executions(matter_id, created_at);
"""
