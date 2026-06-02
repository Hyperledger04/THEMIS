-- Migration 004: Playbook execution DAG tracking table
--
-- WHY: Storing execution records in Postgres lets the UI show historical
-- playbook runs per matter and lets ops audit which positions were flagged.
-- The PlaybookRepository.setup() creates this via DDL; this file is the
-- equivalent migration for managed Postgres environments.

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
