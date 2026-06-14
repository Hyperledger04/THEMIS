-- V3 Phase 5 — Authority verification + §11A corpus partitioning fields
-- Safe to re-run: all statements are IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.

-- §11A Failure Mode 1 — Citation Drift: add ratio extraction fields to authorities.
-- §11A Failure Mode 2 — Jurisdictional Conflation: add corpus provenance fields.
ALTER TABLE authorities
    ADD COLUMN IF NOT EXISTS jurisdiction        TEXT NOT NULL DEFAULT 'india',
    ADD COLUMN IF NOT EXISTS country            TEXT NOT NULL DEFAULT 'india',
    ADD COLUMN IF NOT EXISTS court_tier         TEXT NOT NULL DEFAULT 'persuasive_domestic',
    ADD COLUMN IF NOT EXISTS corpus_namespace   TEXT NOT NULL DEFAULT 'corpus:india_sc',
    ADD COLUMN IF NOT EXISTS verified_excerpt   TEXT,
    ADD COLUMN IF NOT EXISTS paragraph_number   TEXT,
    ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'unverified'
        CONSTRAINT ck_authority_verification_status
            CHECK (verification_status IN ('verified', 'partial', 'contradicted', 'unverified'));

-- Index supporting corpus-partitioned retrieval (Research Counsel query pattern).
CREATE INDEX IF NOT EXISTS idx_authorities_corpus
    ON authorities(matter_id, corpus_namespace, court_tier);

-- Index to quickly surface all unverified or contradicted authorities before output.
CREATE INDEX IF NOT EXISTS idx_authorities_verification
    ON authorities(matter_id, verification_status);

-- Research memos — first-class workspace objects (Phase 5).
CREATE TABLE IF NOT EXISTS research_memos (
    memo_id          TEXT PRIMARY KEY,
    matter_id        TEXT NOT NULL REFERENCES matters(matter_id),
    title            TEXT NOT NULL,
    content          TEXT NOT NULL,
    query            TEXT,
    authority_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    agent_run_id     TEXT,
    status           TEXT NOT NULL DEFAULT 'draft',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_memos_matter ON research_memos(matter_id, status);

-- Risk analyses — adversarial critique attached to matter or draft (Phase 5).
CREATE TABLE IF NOT EXISTS risk_analyses (
    risk_id          TEXT PRIMARY KEY,
    matter_id        TEXT NOT NULL REFERENCES matters(matter_id),
    draft_id         TEXT REFERENCES drafts(draft_id),
    title            TEXT NOT NULL,
    summary          TEXT NOT NULL,
    risks            JSONB NOT NULL DEFAULT '[]'::jsonb,
    agent_run_id     TEXT,
    status           TEXT NOT NULL DEFAULT 'draft',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_risks_matter ON risk_analyses(matter_id, draft_id);

-- Style preferences — per-lawyer drafting style extracted from accepted feedback (Phase 6).
-- These are suggestion-only: they never silently rewrite skills or system prompts.
CREATE TABLE IF NOT EXISTS style_preferences (
    preference_id        TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL,
    firm_id              TEXT NOT NULL DEFAULT 'default',
    matter_type          TEXT,
    doc_type             TEXT,
    preference_text      TEXT NOT NULL,
    source_feedback_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_style_prefs_user ON style_preferences(user_id, firm_id, active);

-- Playbook notes — matter-type and court-specific observations (Phase 6).
CREATE TABLE IF NOT EXISTS playbook_notes (
    note_id              TEXT PRIMARY KEY,
    firm_id              TEXT NOT NULL DEFAULT 'default',
    matter_type          TEXT,
    jurisdiction         TEXT,
    court                TEXT,
    observation          TEXT NOT NULL,
    source_feedback_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_playbook_notes_firm ON playbook_notes(firm_id, matter_type, active);
