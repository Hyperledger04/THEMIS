-- LexAgent Agent Runtime — Postgres schema (Provider Agnostic PLAN Phase 1)
-- Extracted from runtime/postgres.py RUNTIME_SCHEMA_SQL as a standalone migration file.
-- Run via: psql $DATABASE_URL -f 001_runtime.sql

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
CREATE INDEX IF NOT EXISTS idx_runs_matter ON agent_runs(matter_id, status);

CREATE TABLE IF NOT EXISTS agent_jobs (
    job_id             TEXT PRIMARY KEY,
    matter_id          TEXT NOT NULL,
    run_id             TEXT NOT NULL REFERENCES agent_runs(run_id),
    type               TEXT NOT NULL,
    agent              TEXT NOT NULL,
    status             TEXT NOT NULL,
    requires_approval  BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL,
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    error              TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON agent_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_run    ON agent_jobs(run_id);

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
    status           TEXT NOT NULL DEFAULT 'pending',
    approved_by      TEXT,
    approved_at      TIMESTAMPTZ,
    approval_notes   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON agent_approvals(status);

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
CREATE INDEX IF NOT EXISTS idx_notifications_status ON agent_notifications(status);
