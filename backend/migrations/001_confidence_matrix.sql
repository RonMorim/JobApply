-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 001 — Active Confidence Matrix
-- Target: backend/jobs.db  (SQLite)
--
-- Run once:
--   sqlite3 backend/jobs.db < backend/migrations/001_confidence_matrix.sql
--
-- Safe to re-run: all CREATE TABLE statements use IF NOT EXISTS.
-- The app's _migrate() in db.py also calls this logic at startup.
-- ─────────────────────────────────────────────────────────────────────────────

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ── 1. Knowledge Graph Nodes ─────────────────────────────────────────────────
-- One row per unique skill / trait / domain / experience for a user.
-- confidence_score is ALWAYS derived; update only via ProfileUpdateService.

CREATE TABLE IF NOT EXISTS profile_entities (
    entity_id           TEXT        PRIMARY KEY,
    user_id             TEXT        NOT NULL,
    entity_type         TEXT        NOT NULL
                            CHECK (entity_type IN ('skill', 'trait', 'domain', 'experience')),
    name                TEXT        NOT NULL,
    normalized_name     TEXT        NOT NULL,
    confidence_score    REAL        NOT NULL DEFAULT 0.0
                            CHECK (confidence_score BETWEEN 0.0 AND 100.0),
    verification_status TEXT        NOT NULL DEFAULT 'unverified'
                            CHECK (verification_status IN
                                ('unverified', 'needs_evidence', 'partial', 'verified')),
    last_evidence_at    TEXT,           -- ISO-8601 UTC
    created_at          TEXT        NOT NULL,
    updated_at          TEXT        NOT NULL,

    UNIQUE (user_id, normalized_name, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_pe_user
    ON profile_entities (user_id);
CREATE INDEX IF NOT EXISTS idx_pe_user_type
    ON profile_entities (user_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_pe_user_score
    ON profile_entities (user_id, confidence_score DESC);


-- ── 2. Immutable Evidence Ledger ─────────────────────────────────────────────
-- Append-only. Never UPDATE or DELETE rows.
-- Each row = one atomic piece of evidence that contributed to a score.
--
-- base_weight tiers (enforced at service layer):
--   cv_parse          20–35
--   self_assessment   10–25
--   certification     40–60
--   portfolio         45–65
--   conversation_star 65–90  (scaled by extraction_confidence)

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id         TEXT        PRIMARY KEY,
    entity_id           TEXT        NOT NULL
                            REFERENCES profile_entities (entity_id),
    user_id             TEXT        NOT NULL,
    source_type         TEXT        NOT NULL
                            CHECK (source_type IN (
                                'cv_parse', 'self_assertion',
                                'contextual_reinforcement',
                                'certification', 'portfolio',
                                'conversation_star',
                                'negative_flag'
                            )),
    -- base_weight is REAL (unrestricted) — negative_flag rows store negative values.
    base_weight         REAL        NOT NULL,
    raw_content         TEXT,
    verified_at         TEXT        NOT NULL,   -- ISO-8601 UTC
    hard_expires_at     TEXT,                   -- ISO-8601 UTC, nullable
    session_id          TEXT
                            REFERENCES ariel_sessions (session_id),
    event_id            TEXT
                            REFERENCES conversation_events (event_id),
    metadata            TEXT        -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_er_entity
    ON evidence_records (entity_id, verified_at DESC);
CREATE INDEX IF NOT EXISTS idx_er_user
    ON evidence_records (user_id, source_type);
CREATE INDEX IF NOT EXISTS idx_er_session
    ON evidence_records (session_id);


-- ── 3. Ariel Sessions ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ariel_sessions (
    session_id              TEXT    PRIMARY KEY,
    user_id                 TEXT    NOT NULL,
    session_type            TEXT    NOT NULL
                                CHECK (session_type IN (
                                    'gap_analysis',
                                    'behavioral_interview',
                                    'continuous_profiling',
                                    'onboarding'
                                )),
    target_job_id           TEXT,
    target_entities         TEXT,   -- JSON array of entity_ids
    ariel_goal              TEXT,
    status                  TEXT    NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'completed', 'abandoned')),
    transcript_json         TEXT,   -- full message log (append-only at app level)
    confidence_delta_total  REAL    NOT NULL DEFAULT 0.0,
    started_at              TEXT    NOT NULL,
    ended_at                TEXT
);

CREATE INDEX IF NOT EXISTS idx_as_user
    ON ariel_sessions (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_as_job
    ON ariel_sessions (target_job_id);


-- ── 4. Conversation Events ───────────────────────────────────────────────────
-- One row per STAR-method behavioral event extracted by the LLM from a session.

CREATE TABLE IF NOT EXISTS conversation_events (
    event_id                TEXT    PRIMARY KEY,
    session_id              TEXT    NOT NULL
                                REFERENCES ariel_sessions (session_id),
    user_id                 TEXT    NOT NULL,
    star_situation          TEXT,
    star_task               TEXT,
    star_action             TEXT,
    star_result             TEXT,
    extracted_entity_ids    TEXT    NOT NULL,   -- JSON array
    extraction_confidence   REAL    NOT NULL
                                CHECK (extraction_confidence BETWEEN 0.0 AND 1.0),
    raw_quote               TEXT,
    analyzed_at             TEXT    NOT NULL    -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_ce_session
    ON conversation_events (session_id);
CREATE INDEX IF NOT EXISTS idx_ce_user
    ON conversation_events (user_id, analyzed_at DESC);


-- ── 5. Confidence Audit Log ──────────────────────────────────────────────────
-- Immutable. Every confidence_score change writes one row here.

CREATE TABLE IF NOT EXISTS confidence_audit_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT    NOT NULL
                        REFERENCES profile_entities (entity_id),
    user_id         TEXT    NOT NULL,
    old_score       REAL    NOT NULL,
    new_score       REAL    NOT NULL,
    delta           REAL    NOT NULL,   -- new - old (signed)
    trigger_source  TEXT    NOT NULL,
    evidence_id     TEXT    REFERENCES evidence_records (evidence_id),
    session_id      TEXT    REFERENCES ariel_sessions (session_id),
    changed_at      TEXT    NOT NULL,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_cal_entity
    ON confidence_audit_log (entity_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cal_user
    ON confidence_audit_log (user_id, changed_at DESC);


-- ── 6. Ariel Gap Queue ───────────────────────────────────────────────────────
-- Ariel's work queue: entities that are weak or missing for priority jobs.

CREATE TABLE IF NOT EXISTS ariel_gap_queue (
    gap_id              TEXT    PRIMARY KEY,
    user_id             TEXT    NOT NULL,
    entity_id           TEXT    NOT NULL
                            REFERENCES profile_entities (entity_id),
    job_id              TEXT,
    current_confidence  REAL    NOT NULL,
    required_confidence REAL    NOT NULL,
    gap_severity        TEXT    NOT NULL
                            CHECK (gap_severity IN ('critical', 'moderate', 'minor')),
    status              TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN (
                                'pending', 'in_session', 'resolved', 'dismissed'
                            )),
    session_id          TEXT    REFERENCES ariel_sessions (session_id),
    detected_at         TEXT    NOT NULL,
    resolved_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_agq_user
    ON ariel_gap_queue (user_id, gap_severity, status);
CREATE INDEX IF NOT EXISTS idx_agq_job
    ON ariel_gap_queue (job_id, status);
