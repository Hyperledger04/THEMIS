-- Migration 003: Runtime Brakes — cost tracking, halt state, phase gates
--
-- WHY: All new columns have DEFAULT values so existing rows are populated
-- correctly without a backfill. Deploy order: run this migration BEFORE
-- deploying the new worker code that reads these columns.

ALTER TABLE agent_runs
    ADD COLUMN IF NOT EXISTS cost_total_usd  NUMERIC(12,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cost_cap_reached BOOLEAN       NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS halt_state       TEXT;

ALTER TABLE agent_jobs
    ADD COLUMN IF NOT EXISTS cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_activity_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS current_phase    TEXT DEFAULT 'init',
    ADD COLUMN IF NOT EXISTS phase_gates      JSONB NOT NULL DEFAULT '{}'::jsonb;
