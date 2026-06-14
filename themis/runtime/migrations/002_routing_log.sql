-- Migration 002: inference routing log
-- Tracks every LLM call: provider, model, tier, tokens, cost, anonymization status.
-- Separate from audit_log (which tracks access/compliance events) — this table
-- tracks LLM call economics for billing dashboards and cost cap enforcement.

CREATE TABLE IF NOT EXISTS inference_routing_log (
    log_id          TEXT        PRIMARY KEY,
    matter_id       TEXT,
    firm_id         TEXT        NOT NULL DEFAULT 'default',
    provider        TEXT        NOT NULL DEFAULT 'unknown',
    model           TEXT        NOT NULL DEFAULT 'unknown',
    inference_tier  INTEGER     NOT NULL DEFAULT 4,
    input_tokens    INTEGER     NOT NULL DEFAULT 0,
    output_tokens   INTEGER     NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0,
    anonymized      BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_routing_log_matter
    ON inference_routing_log(matter_id, created_at);

CREATE INDEX IF NOT EXISTS idx_routing_log_firm
    ON inference_routing_log(firm_id, created_at);

-- SQLite-compatible variant (used in personal mode) — NUMERIC(12,6) → REAL,
-- TIMESTAMPTZ → TEXT, BOOLEAN → INTEGER, DEFAULT NOW() → CURRENT_TIMESTAMP.
-- Applied conditionally in session_store.py when postgres_url is None.
