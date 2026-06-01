-- LexAgent Matter Workspace — Canonical Postgres schema (V3 Phase 2)
-- Run via: psql $DATABASE_URL -f 001_workspace.sql
-- All timestamps are TIMESTAMPTZ. Soft-delete via status fields (no hard DELETEs on legal objects).

CREATE TABLE IF NOT EXISTS matters (
    matter_id   TEXT PRIMARY KEY,
    firm_id     TEXT NOT NULL DEFAULT 'default',
    user_id     TEXT NOT NULL DEFAULT 'default',
    title       TEXT NOT NULL,
    matter_type TEXT NOT NULL,
    jurisdiction TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_matters_firm ON matters(firm_id, status);

CREATE TABLE IF NOT EXISTS parties (
    party_id   TEXT PRIMARY KEY,
    matter_id  TEXT NOT NULL REFERENCES matters(matter_id),
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'other',
    address    TEXT,
    contact    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_parties_matter ON parties(matter_id);

CREATE TABLE IF NOT EXISTS documents (
    document_id  TEXT PRIMARY KEY,
    matter_id    TEXT NOT NULL REFERENCES matters(matter_id),
    firm_id      TEXT NOT NULL DEFAULT 'default',
    filename     TEXT NOT NULL,
    mime_type    TEXT,
    storage_uri  TEXT NOT NULL,
    parser       TEXT NOT NULL DEFAULT 'unknown',
    page_count   INTEGER,
    status       TEXT NOT NULL DEFAULT 'uploaded',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_matter ON documents(matter_id, status);

CREATE TABLE IF NOT EXISTS source_anchors (
    anchor_id          TEXT PRIMARY KEY,
    matter_id          TEXT NOT NULL REFERENCES matters(matter_id),
    document_id        TEXT NOT NULL REFERENCES documents(document_id),
    page               INTEGER,
    line_start         INTEGER,
    line_end           INTEGER,
    excerpt            TEXT NOT NULL,
    confidence         DOUBLE PRECISION NOT NULL DEFAULT 0,
    extractor_agent    TEXT,
    extraction_run_id  TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_anchors_document ON source_anchors(document_id, page);

CREATE TABLE IF NOT EXISTS extracted_facts (
    fact_id              TEXT PRIMARY KEY,
    matter_id            TEXT NOT NULL REFERENCES matters(matter_id),
    text                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'extracted',
    confidence           DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_anchor_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    extractor_agent      TEXT,
    extraction_run_id    TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_facts_matter ON extracted_facts(matter_id, status);

CREATE TABLE IF NOT EXISTS issues (
    issue_id          TEXT PRIMARY KEY,
    matter_id         TEXT NOT NULL REFERENCES matters(matter_id),
    text              TEXT NOT NULL,
    category          TEXT,
    status            TEXT NOT NULL DEFAULT 'open',
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chronology_items (
    chronology_id        TEXT PRIMARY KEY,
    matter_id            TEXT NOT NULL REFERENCES matters(matter_id),
    date_text            TEXT NOT NULL,
    event                TEXT NOT NULL,
    normalized_date      DATE,
    confidence           DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_anchor_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,
    extractor_agent      TEXT,
    extraction_run_id    TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chrono_matter ON chronology_items(matter_id, normalized_date);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id       TEXT PRIMARY KEY,
    matter_id         TEXT NOT NULL REFERENCES matters(matter_id),
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    document_id       TEXT REFERENCES documents(document_id),
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence        DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS authorities (
    authority_id      TEXT PRIMARY KEY,
    matter_id         TEXT NOT NULL REFERENCES matters(matter_id),
    authority_type    TEXT NOT NULL DEFAULT 'case',
    title             TEXT NOT NULL,
    citation          TEXT,
    court             TEXT,
    url               TEXT,
    proposition       TEXT NOT NULL,
    treatment         TEXT NOT NULL DEFAULT 'unknown',
    verified          BOOLEAN NOT NULL DEFAULT FALSE,
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_authorities_matter ON authorities(matter_id, verified);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id                TEXT PRIMARY KEY,
    matter_id               TEXT NOT NULL REFERENCES matters(matter_id),
    doc_type                TEXT NOT NULL,
    version                 INTEGER NOT NULL DEFAULT 1,
    content                 TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'draft',
    verification_report_id  TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_drafts_matter ON drafts(matter_id, status);

CREATE TABLE IF NOT EXISTS feedback_items (
    feedback_id  TEXT PRIMARY KEY,
    matter_id    TEXT REFERENCES matters(matter_id),
    user_id      TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT,
    signal       TEXT NOT NULL,
    note         TEXT,
    diff         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deadlines (
    deadline_id       TEXT PRIMARY KEY,
    matter_id         TEXT NOT NULL REFERENCES matters(matter_id),
    title             TEXT NOT NULL,
    due_date          DATE NOT NULL,
    deadline_type     TEXT NOT NULL DEFAULT 'other',
    status            TEXT NOT NULL DEFAULT 'upcoming',
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deadlines_matter ON deadlines(matter_id, due_date, status);

CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    matter_id   TEXT NOT NULL REFERENCES matters(matter_id),
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    assigned_to TEXT,
    due_date    DATE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_matter ON tasks(matter_id, status);
