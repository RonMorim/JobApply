"""
Database engine, ORM models, and table initialisation.

Uses SQLite so no external server is required.
Tables are created automatically on first startup via init_db().
Columns added in later versions are applied safely via _migrate().
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Boolean, Column, Float, Integer, String, Text, create_engine, text
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON

# Place jobs.db next to main.py inside the backend/ directory
_DB_PATH = Path(__file__).resolve().parent.parent / "jobs.db"
ENGINE   = create_engine(
    f"sqlite:///{_DB_PATH}",
    connect_args={"check_same_thread": False},
)


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    """One row = one analyzed JobMatch, fully serialised for SQLite."""
    __tablename__ = "jobs"

    job_id                = Column(String,  primary_key=True)
    title                 = Column(String,  nullable=False)
    company               = Column(String,  nullable=False)
    location              = Column(String,  nullable=False, default="Unknown")
    score                 = Column(Float,   nullable=False, default=0.0)
    confidence_score      = Column(Integer, nullable=False, default=50)
    culture_fit_score     = Column(Integer, nullable=False, default=50)
    trajectory_alignment  = Column(Text,    nullable=False, default="")
    company_dna_inference = Column(Text,    nullable=False, default="")
    # Nested structures stored as JSON
    investigation_points  = Column(JSON, nullable=False, default=list)
    detailed_analysis     = Column(JSON, nullable=False, default=dict)
    reasons               = Column(JSON, nullable=False, default=list)
    # Optional / nullable fields
    apply_url             = Column(String,  nullable=True)
    is_new                = Column(Boolean, nullable=False, default=True)
    posted_at             = Column(String,  nullable=False, default="")
    why_ron               = Column(Text,    nullable=True)
    scoring_rationale     = Column(Text,    nullable=True)
    category              = Column(String,  nullable=True)
    # Cached tailored CV — set by the tailor endpoint after first generation
    # Shape: {"cv_data": {...}, "match_score": {...}}
    tailored_cv           = Column(JSON, nullable=True)
    # Application status
    applied               = Column(Boolean, nullable=False, default=False)
    applied_at            = Column(String,  nullable=True)
    # Origin and liveness
    source                = Column(String,  nullable=False, default='automatic')
    is_open               = Column(Boolean, nullable=False, default=True)
    # Raw JD text — stored so batch scoring never re-scrapes
    jd_text               = Column(Text,    nullable=True)
    # LLM-structured JD stored as JSON string (set by jd_structure_service)
    jd_structured         = Column(Text,    nullable=True)
    # Multi-user & feed columns
    user_id               = Column(String,  nullable=False, default='default', index=True)
    source_type           = Column(String,  nullable=False, default='other')
    company_website_url   = Column(String,  nullable=True)
    status                = Column(String,  nullable=False, default='new')
    match_score           = Column(Float,   nullable=False, default=0.0)
    score_is_proxy        = Column(Boolean, nullable=False, default=True)
    created_at            = Column(String,  nullable=True)  # ISO-8601 UTC
    # Language hint: 'he' (Hebrew) | 'en' (English) | None (unknown)
    locale                = Column(String,  nullable=True)
    # Cross-board dedup fingerprint: sha1(norm(title)|norm(company)|norm(location))[:16]
    # Shared across multiple boards that post the same role.
    dedup_key             = Column(String,  nullable=True, index=True)
    # Incremented each time s2 LLM enrichment returns a non-substantive result.
    # UI uses this to show a hard-failure state after 3 failed attempts.
    enrichment_failures   = Column(Integer, nullable=False, default=0)
    # Phase 3 — generated hiring-manager outreach message; persists across reloads.
    outreach_text         = Column(Text,    nullable=True)


class ProfileInterviewRow(Base):
    """
    Persistent state for a conversational profile-building interview session.

    Each session is a multi-turn dialogue where the agent:
      1. Collects career facts through open-ended questions
      2. Extracts structured data into draft_profile
      3. Assigns confidence scores to every extracted claim
      4. Requests document uploads to upgrade unverified claims to 100%

    draft_profile  — mirrors USER_PROFILE schema; null until first extraction
    confidence_map — flat dict: {claim_id: {score, status, missing, evidence}}
                     claim_id examples: "education.0.degree", "experience.1.role"
    pending_probes — list of targeted follow-up questions still to be asked
    document_refs  — list of {filename, claim_id, status, extracted_text}
    user_id        — owning user; all queries must be scoped to this value
    """
    __tablename__ = "profile_interviews"

    session_id     = Column(String, primary_key=True)
    # Multi-tenant owner — added in v2; existing rows migrated to 'default'
    user_id        = Column(String, nullable=False, default="default", index=True)
    messages       = Column(JSON, nullable=False, default=list)
    draft_profile  = Column(JSON, nullable=True)
    confidence_map = Column(JSON, nullable=True)
    pending_probes = Column(JSON, nullable=True, default=list)
    document_refs  = Column(JSON, nullable=True, default=list)
    status         = Column(String, nullable=False, default="active")
    # "optimize_gaps" → Jonathan mode; None → Adam (default builder)
    intent         = Column(String, nullable=True)
    created_at     = Column(String, nullable=True)
    updated_at     = Column(String, nullable=True)


class KVRow(Base):
    """
    Lightweight key-value store for ephemeral system state.

    Used for transient values that don't justify a dedicated table:
      • gmail_verification_code — 9-digit code intercepted from Google's
        forwarding confirmation email; read by the frontend modal poller
        and discarded after 30 minutes.

    Schema is intentionally minimal: key is always a short ASCII string,
    value is text, updated_at is an ISO-8601 UTC string for TTL checks.
    """
    __tablename__ = "kv_store"

    key        = Column(String, primary_key=True)
    value      = Column(Text,   nullable=False, default="")
    updated_at = Column(String, nullable=False, default="")


class ApplicationRow(Base):
    """One row = one submitted application."""
    __tablename__ = "applications"

    application_id = Column(String, primary_key=True)
    # Multi-tenant owner — added in v2; existing rows migrated to 'default'
    user_id        = Column(String, nullable=False, default="default", index=True)
    job_id         = Column(String, nullable=False, index=True)
    title          = Column(String, nullable=False)
    company        = Column(String, nullable=False)
    ats            = Column(String, nullable=False, default="Direct")
    status         = Column(String, nullable=False, default="submitted")
    submitted_at   = Column(String, nullable=False)
    last_update    = Column(String, nullable=False)
    score          = Column(Float,  nullable=False, default=0.0)
    cover_letter   = Column(Text,   nullable=True)
    reason         = Column(Text,   nullable=True)


class RecruiterReplyDraftRow(Base):
    """
    Phase 6 — AI-drafted reply to an inbound recruiter email.

    One row per drafted reply, linked to the owning user and the job whose
    application the recruiter email referred to. Drafts are never sent
    automatically — the user reviews them in the dashboard first.

    Table is created by Base.metadata.create_all() in init_db() on startup.
    """
    __tablename__ = "recruiter_reply_drafts"

    draft_id      = Column(String, primary_key=True)
    user_id       = Column(String, nullable=False, index=True)
    job_id        = Column(String, nullable=False, index=True)
    # Sanitized excerpt of the inbound email the draft responds to (audit trail)
    email_excerpt = Column(Text,   nullable=False, default="")
    draft_text    = Column(Text,   nullable=False, default="")
    status        = Column(String, nullable=False, default="draft")  # draft | sent | discarded
    created_at    = Column(String, nullable=False, default="")


def _migrate() -> None:
    """Add columns introduced after the initial schema without dropping data."""

    # ── profile_interviews — add user_id (v2) + intent (v3) ─────────────────
    with ENGINE.connect() as conn:
        existing_pi = {row[1] for row in conn.execute(text("PRAGMA table_info(profile_interviews)"))}
        if "user_id" not in existing_pi:
            conn.execute(text(
                "ALTER TABLE profile_interviews ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_profile_interviews_user_id "
                "ON profile_interviews (user_id)"
            ))
            conn.commit()
        if "intent" not in existing_pi:
            conn.execute(text(
                "ALTER TABLE profile_interviews ADD COLUMN intent TEXT"
            ))
            conn.commit()

    # ── applications — add user_id (v2) ──────────────────────────────────────
    with ENGINE.connect() as conn:
        existing_app = {row[1] for row in conn.execute(text("PRAGMA table_info(applications)"))}
        if "user_id" not in existing_app:
            conn.execute(text(
                "ALTER TABLE applications ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_applications_user_id "
                "ON applications (user_id)"
            ))
            conn.commit()

    # ── master_profiles — add is_admin (Phase 2 admin foundation) ────────────
    with ENGINE.connect() as conn:
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "master_profiles" in tables:
            existing_mp = {row[1] for row in conn.execute(text("PRAGMA table_info(master_profiles)"))}
            if "is_admin" not in existing_mp:
                conn.execute(text(
                    "ALTER TABLE master_profiles ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"
                ))
                conn.commit()
            if "email" not in existing_mp:
                conn.execute(text(
                    "ALTER TABLE master_profiles ADD COLUMN email TEXT"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_master_profiles_email "
                    "ON master_profiles (email)"
                ))
                conn.commit()

    # ── master_profiles — create if not yet present (safe on existing DBs) ──────
    with ENGINE.connect() as conn:
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        if "master_profiles" not in tables:
            conn.execute(text("""
                CREATE TABLE master_profiles (
                    user_id           TEXT PRIMARY KEY,
                    onboarding_status TEXT NOT NULL DEFAULT 'incomplete',
                    master_profile    JSON NOT NULL DEFAULT '{}',
                    created_at        TEXT,
                    updated_at        TEXT
                )
            """))
            conn.commit()

    new_job_columns = [
        ("applied",              "BOOLEAN NOT NULL DEFAULT 0"),
        ("applied_at",           "TEXT"),
        ("source",               "TEXT NOT NULL DEFAULT 'automatic'"),
        ("is_open",              "BOOLEAN NOT NULL DEFAULT 1"),
        ("scoring_rationale",    "TEXT"),
        ("tailored_cv",          "JSON"),
        ("jd_text",              "TEXT"),
        ("user_id",              "TEXT NOT NULL DEFAULT 'default'"),
        ("source_type",          "TEXT NOT NULL DEFAULT 'other'"),
        ("company_website_url",  "TEXT"),
        ("status",               "TEXT NOT NULL DEFAULT 'new'"),
        ("match_score",          "REAL NOT NULL DEFAULT 0.0"),
        ("score_is_proxy",       "BOOLEAN NOT NULL DEFAULT 1"),
        ("created_at",           "TEXT"),
        ("locale",               "TEXT"),
        ("dedup_key",            "TEXT"),
        ("jd_structured",        "TEXT"),
        ("enrichment_failures",  "INTEGER NOT NULL DEFAULT 0"),
        ("outreach_text",        "TEXT"),   # Phase 3 — persisted outreach message
    ]
    with ENGINE.connect() as conn:
        result  = conn.execute(text("PRAGMA table_info(jobs)"))
        existing = {row[1] for row in result}
        for col, definition in new_job_columns:
            if col not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col} {definition}"))

        # Add dedup_key index if not already present (SQLite: CREATE INDEX IF NOT EXISTS)
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_jobs_dedup_key ON jobs (dedup_key)"
        ))
        conn.commit()


class MasterProfileRow(Base):
    """
    Central master profile for each authenticated user.

    Stores the complete, unstructured and structured professional history in a
    single JSON document (master_profile) alongside a lightweight onboarding
    state flag.  All Ariel tool calls that mutate profile data write to this
    table — they never touch the legacy flat JSON files.

    master_profile shape (baseline):
    {
        "professional_summary": str,
        "experience": [
            {
                "company":   str,
                "role":      str,
                "start":     str,   # e.g. "2021-03"
                "end":       str,   # e.g. "2024-01" | "present"
                "bullets":   [str]
            }
        ],
        "skills":       [str],
        "education":    [
            {
                "institution": str,
                "degree":      str,
                "field":       str,
                "year":        str
            }
        ],
        "career_goals": {
            "target_roles":        [str],
            "preferred_locations": [str],
            "work_environment":    str,   # "remote" | "hybrid" | "onsite" | "any"
            "notes":               str
        }
    }

    onboarding_status:
        "incomplete" — default; Ariel is still collecting information
        "complete"   — user confirmed all background has been provided;
                       set exclusively by the finalize_onboarding tool
    """
    __tablename__ = "master_profiles"

    user_id            = Column(String, primary_key=True)
    # Verified email from the Supabase JWT — lower-cased. Used by
    # POST /api/auth/sync-user to link accounts across auth providers
    # (email login vs Google OAuth) when Supabase issues a different `sub`
    # for the same person.
    email              = Column(String, nullable=True, index=True)
    onboarding_status  = Column(String, nullable=False, default="incomplete")
    master_profile     = Column(JSON,   nullable=False, default=dict)
    # Admin-dashboard foundation (Phase 2) — flipped manually in the DB for
    # now; require_admin (api/deps.py) is the only consumer.
    is_admin           = Column(Boolean, nullable=False, default=False)
    created_at         = Column(String, nullable=True)
    updated_at         = Column(String, nullable=True)


# ── Active Confidence Matrix ORM models ──────────────────────────────────────
# These six tables form the knowledge-graph backbone for the Ariel agent.
# ProfileUpdateService is the only writer; never UPDATE confidence_score directly.

class ProfileEntityRow(Base):
    """Knowledge graph node: one skill / trait / domain / experience per row."""
    __tablename__ = "profile_entities"

    entity_id              = Column(String,  primary_key=True)
    user_id                = Column(String,  nullable=False, index=True)
    entity_type            = Column(String,  nullable=False)   # skill|trait|domain|experience
    name                   = Column(String,  nullable=False)
    normalized_name        = Column(String,  nullable=False)
    confidence_score       = Column(Float,   nullable=False, default=0.0)
    verification_status    = Column(String,  nullable=False, default="unverified")
    # Set to 1 by ingest_negative_flag when score < MANUAL_REVIEW_THRESHOLD.
    # Cleared to 0 whenever a positive evidence ingest pushes score back above threshold.
    # Stored as INTEGER (0/1) to avoid SQLite CHECK constraint issues with a new string value.
    # server_default matters: ProfileUpdateService writes with raw SQL INSERTs
    # that omit this column, so a fresh create_all() DB needs an SQL-level
    # DEFAULT (Python-side `default=` is invisible to raw SQL) — otherwise
    # every CV ingest fails with a NOT NULL IntegrityError.
    manual_review_required = Column(Integer, nullable=False, default=0, server_default="0")
    # Hierarchical skill tier — set during evidence ingest by ProfileUpdateService.
    # Core_Mastery:       direct hands-on proficiency, no AI assistance.
    # System_Orchestration: understands architecture; uses AI for boilerplate.
    # NULL until enough evidence is available to classify.
    skill_tier             = Column(String,  nullable=True)
    # Self-reported proficiency level, set when the user states their level in
    # chat (e.g. 'Beginner'/'Intermediate'/'Advanced'/'Expert'). Adjusted by
    # ProfileUpdateService.apply_chat_proficiency_update — NULL until the user
    # explicitly clarifies their level. Independent of skill_tier (which is
    # derived from evidence AI-assistance, not from the user's stated level).
    proficiency_level      = Column(String,  nullable=True)
    # Truth-based decoupled scores — populated by compute_decoupled_score().
    # architecture_confidence: score from portfolio / STAR / CV evidence.
    # syntax_confidence:       score from manual_assessment evidence only.
    # verification_level:      VERIFIED_MANUAL | ORCHESTRATION_ONLY | UNVERIFIED
    architecture_confidence = Column(Float,  nullable=False, default=0.0, server_default="0.0")
    syntax_confidence       = Column(Float,  nullable=False, default=0.0, server_default="0.0")
    verification_level      = Column(String, nullable=False, default="UNVERIFIED", server_default="UNVERIFIED")
    last_evidence_at       = Column(String,  nullable=True)
    created_at             = Column(String,  nullable=False)
    updated_at             = Column(String,  nullable=False)


class EvidenceRecordRow(Base):
    """Immutable evidence ledger — append-only, never UPDATE or DELETE."""
    __tablename__ = "evidence_records"

    evidence_id     = Column(String,  primary_key=True)
    entity_id       = Column(String,  nullable=False, index=True)
    user_id         = Column(String,  nullable=False, index=True)
    source_type     = Column(String,  nullable=False)
    base_weight     = Column(Float,   nullable=False)
    raw_content     = Column(Text,    nullable=True)
    verified_at     = Column(String,  nullable=False)
    hard_expires_at = Column(String,  nullable=True)
    session_id      = Column(String,  nullable=True, index=True)
    event_id        = Column(String,  nullable=True)
    extra_metadata  = Column(Text,    nullable=True)   # JSON blob — 'metadata' is reserved by SQLAlchemy
    # True when the candidate used AI to generate boilerplate but understood
    # the architecture.  Triggers AI_AUGMENTATION_PENALTY (×0.6) in scoring.
    # server_default for the same reason as profile_entities: evidence rows are
    # written via raw SQL INSERTs that omit this column.
    is_ai_assisted  = Column(Integer, nullable=False, default=0, server_default="0")


class ShadowScoreRow(Base):
    """
    Shadow-mode calibration log for the ATS Match Engine.

    One row per scored job: the production composite the user actually saw,
    alongside the new engine's score and full component breakdown. Append-only;
    consumed later by the weight-calibration analysis. Safe to truncate after
    calibration.
    """
    __tablename__ = "shadow_match_scores"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(String,  nullable=False, index=True)
    job_title      = Column(String,  nullable=True)
    company        = Column(String,  nullable=True)
    existing_score = Column(Float,   nullable=False)   # what the frontend received
    ats_score      = Column(Float,   nullable=False)   # new engine's final_score
    breakdown_json = Column(Text,    nullable=False, default="{}")  # AtsMatchResult dump
    created_at     = Column(String,  nullable=False)


class CompanyIntelRow(Base):
    """
    Cached CompanyProfile from the Company Intelligence Agent.

    One row per normalized company name. Profiles older than the service's
    staleness window (30 days) are served stale-while-revalidate: returned
    immediately while a background refresh re-researches recent news
    (layoffs, acquisitions, pivots).
    """
    __tablename__ = "company_intel"

    company_key   = Column(String, primary_key=True)              # normalized lowercase name
    display_name  = Column(String, nullable=False)
    profile_json  = Column(Text,   nullable=False, default="{}")  # CompanyProfile dump
    researched_at = Column(String, nullable=False)                # ISO 8601 UTC


class ArielSessionRow(Base):
    """One purposeful Ariel conversation session."""
    __tablename__ = "ariel_sessions"

    session_id             = Column(String, primary_key=True)
    user_id                = Column(String, nullable=False, index=True)
    session_type           = Column(String, nullable=False)
    target_job_id          = Column(String, nullable=True, index=True)
    target_entities        = Column(Text,   nullable=True)    # JSON array
    ariel_goal             = Column(Text,   nullable=True)
    status                 = Column(String, nullable=False, default="active")
    transcript_json        = Column(Text,   nullable=True)
    confidence_delta_total = Column(Float,  nullable=False, default=0.0)
    started_at             = Column(String, nullable=False)
    ended_at               = Column(String, nullable=True)


class ConversationEventRow(Base):
    """One STAR behavioral event extracted by the LLM from a session transcript."""
    __tablename__ = "conversation_events"

    event_id              = Column(String, primary_key=True)
    session_id            = Column(String, nullable=False, index=True)
    user_id               = Column(String, nullable=False, index=True)
    star_situation        = Column(Text,   nullable=True)
    star_task             = Column(Text,   nullable=True)
    star_action           = Column(Text,   nullable=True)
    star_result           = Column(Text,   nullable=True)
    extracted_entity_ids  = Column(Text,   nullable=False)   # JSON array
    extraction_confidence = Column(Float,  nullable=False)
    raw_quote             = Column(Text,   nullable=True)
    analyzed_at           = Column(String, nullable=False)


class ConfidenceAuditLogRow(Base):
    """Immutable audit trail — one row per confidence_score change."""
    __tablename__ = "confidence_audit_log"

    log_id         = Column(Integer, primary_key=True, autoincrement=True)
    entity_id      = Column(String,  nullable=False, index=True)
    user_id        = Column(String,  nullable=False, index=True)
    old_score      = Column(Float,   nullable=False)
    new_score      = Column(Float,   nullable=False)
    delta          = Column(Float,   nullable=False)
    trigger_source = Column(String,  nullable=False)
    evidence_id    = Column(String,  nullable=True)
    session_id     = Column(String,  nullable=True)
    changed_at     = Column(String,  nullable=False)
    note           = Column(Text,    nullable=True)


class ArielGapQueueRow(Base):
    """Ariel's work queue: skills/traits that need evidence for priority jobs."""
    __tablename__ = "ariel_gap_queue"

    gap_id              = Column(String, primary_key=True)
    user_id             = Column(String, nullable=False, index=True)
    entity_id           = Column(String, nullable=False)
    job_id              = Column(String, nullable=True,  index=True)
    current_confidence  = Column(Float,  nullable=False)
    required_confidence = Column(Float,  nullable=False)
    gap_severity        = Column(String, nullable=False)
    status              = Column(String, nullable=False, default="pending")
    session_id          = Column(String, nullable=True)
    detected_at         = Column(String, nullable=False)
    resolved_at         = Column(String, nullable=True)


def _migrate_confidence_matrix(conn) -> None:
    """
    Idempotent migration for the Active Confidence Matrix tables (migration 001).
    Creates each table only if it doesn't already exist.
    Matches the SQL in backend/migrations/001_confidence_matrix.sql.
    """
    tables = {
        row[0]
        for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }

    # All six tables are created by Base.metadata.create_all() above if the DB
    # is fresh.  For existing DBs the tables won't be in the ORM metadata yet,
    # so we run the raw CREATE TABLE IF NOT EXISTS statements here.
    if "profile_entities" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS profile_entities (
                entity_id              TEXT PRIMARY KEY,
                user_id                TEXT NOT NULL,
                entity_type            TEXT NOT NULL,
                name                   TEXT NOT NULL,
                normalized_name        TEXT NOT NULL,
                confidence_score       REAL NOT NULL DEFAULT 0.0,
                verification_status    TEXT NOT NULL DEFAULT 'unverified',
                manual_review_required INTEGER NOT NULL DEFAULT 0,
                last_evidence_at       TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL,
                UNIQUE (user_id, normalized_name, entity_type)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pe_user ON profile_entities (user_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_pe_user_score ON profile_entities (user_id, confidence_score DESC)"))

    if "ariel_sessions" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ariel_sessions (
                session_id              TEXT PRIMARY KEY,
                user_id                 TEXT NOT NULL,
                session_type            TEXT NOT NULL,
                target_job_id           TEXT,
                target_entities         TEXT,
                ariel_goal              TEXT,
                status                  TEXT NOT NULL DEFAULT 'active',
                transcript_json         TEXT,
                confidence_delta_total  REAL NOT NULL DEFAULT 0.0,
                started_at              TEXT NOT NULL,
                ended_at                TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_as_user ON ariel_sessions (user_id, started_at DESC)"))

    if "conversation_events" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS conversation_events (
                event_id                TEXT PRIMARY KEY,
                session_id              TEXT NOT NULL REFERENCES ariel_sessions (session_id),
                user_id                 TEXT NOT NULL,
                star_situation          TEXT,
                star_task               TEXT,
                star_action             TEXT,
                star_result             TEXT,
                extracted_entity_ids    TEXT NOT NULL,
                extraction_confidence   REAL NOT NULL,
                raw_quote               TEXT,
                analyzed_at             TEXT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ce_session ON conversation_events (session_id)"))

    # Full CREATE DDL for evidence_records — includes all source_type values.
    # base_weight is REAL (not constrained to positive) so negative_flag rows
    # can store negative weights.
    _EVIDENCE_RECORDS_DDL = """
        CREATE TABLE evidence_records (
            evidence_id     TEXT PRIMARY KEY,
            entity_id       TEXT NOT NULL REFERENCES profile_entities (entity_id),
            user_id         TEXT NOT NULL,
            source_type     TEXT NOT NULL
                                CHECK (source_type IN (
                                    'cv_parse', 'self_assertion',
                                    'contextual_reinforcement',
                                    'certification', 'portfolio',
                                    'conversation_star',
                                    'manual_assessment',
                                    'negative_flag'
                                )),
            base_weight     REAL NOT NULL,
            raw_content     TEXT,
            verified_at     TEXT NOT NULL,
            hard_expires_at TEXT,
            session_id      TEXT REFERENCES ariel_sessions (session_id),
            event_id        TEXT REFERENCES conversation_events (event_id),
            extra_metadata  TEXT
        )
    """

    if "evidence_records" not in tables:
        conn.execute(text(_EVIDENCE_RECORDS_DDL))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_entity ON evidence_records (entity_id, verified_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_user   ON evidence_records (user_id, source_type)"))
    else:
        # ── Migration 003: widen source_type CHECK to include new types ────────
        # Detect a stale constraint by checking whether 'negative_flag' is
        # already present in the CREATE TABLE statement stored in sqlite_master.
        schema_row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_records'")
        ).fetchone()
        if schema_row and "negative_flag" not in schema_row[0]:
            # Recreate the table with the updated CHECK constraint.
            # SQLite requires a 3-step rename-create-copy-drop dance.
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("ALTER TABLE evidence_records RENAME TO evidence_records_old"))
            conn.execute(text(_EVIDENCE_RECORDS_DDL))
            conn.execute(text("""
                INSERT INTO evidence_records
                SELECT * FROM evidence_records_old
            """))
            conn.execute(text("DROP TABLE evidence_records_old"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_entity ON evidence_records (entity_id, verified_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_user   ON evidence_records (user_id, source_type)"))

        # ── Migration 004: rename metadata → extra_metadata ───────────────
        # SQLite doesn't support ALTER TABLE RENAME COLUMN before 3.25.0, so
        # we detect the stale column name and do the rename-copy-drop dance.
        schema_row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_records'")
        ).fetchone()
        if schema_row and "extra_metadata" not in schema_row[0]:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("ALTER TABLE evidence_records RENAME TO evidence_records_old"))
            conn.execute(text(_EVIDENCE_RECORDS_DDL))
            conn.execute(text("""
                INSERT INTO evidence_records
                    (evidence_id, entity_id, user_id, source_type, base_weight,
                     raw_content, verified_at, hard_expires_at, session_id,
                     event_id, extra_metadata)
                SELECT evidence_id, entity_id, user_id, source_type, base_weight,
                       raw_content, verified_at, hard_expires_at, session_id,
                       event_id, metadata
                FROM evidence_records_old
            """))
            conn.execute(text("DROP TABLE evidence_records_old"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_entity ON evidence_records (entity_id, verified_at DESC)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_er_user   ON evidence_records (user_id, source_type)"))

        # ── Migration 005: add is_ai_assisted to evidence_records ─────────────
        er_cols = [r[1] for r in conn.execute(
            text("PRAGMA table_info(evidence_records)")
        ).fetchall()]
        if "is_ai_assisted" not in er_cols:
            conn.execute(text(
                "ALTER TABLE evidence_records ADD COLUMN is_ai_assisted INTEGER NOT NULL DEFAULT 0"
            ))

        # ── Migration 006: add skill_tier to profile_entities ─────────────────
        pe_cols = [r[1] for r in conn.execute(
            text("PRAGMA table_info(profile_entities)")
        ).fetchall()]
        if "skill_tier" not in pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities ADD COLUMN skill_tier TEXT"
            ))

        # ── Migration 007: add decoupled score columns ────────────────────────
        # Re-read cols in case Migration 006 just added one
        pe_cols = [r[1] for r in conn.execute(
            text("PRAGMA table_info(profile_entities)")
        ).fetchall()]
        if "architecture_confidence" not in pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities "
                "ADD COLUMN architecture_confidence REAL NOT NULL DEFAULT 0.0"
            ))
        if "syntax_confidence" not in pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities "
                "ADD COLUMN syntax_confidence REAL NOT NULL DEFAULT 0.0"
            ))
        if "verification_level" not in pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities "
                "ADD COLUMN verification_level TEXT NOT NULL DEFAULT 'UNVERIFIED'"
            ))

        # ── Migration 008: expand evidence_records CHECK for manual_assessment ─
        er_schema = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_records'")
        ).fetchone()
        if er_schema and "manual_assessment" not in er_schema[0]:
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            conn.execute(text("ALTER TABLE evidence_records RENAME TO evidence_records_old"))
            conn.execute(text(_EVIDENCE_RECORDS_DDL))
            conn.execute(text("""
                INSERT INTO evidence_records
                    (evidence_id, entity_id, user_id, source_type, base_weight,
                     raw_content, verified_at, hard_expires_at, session_id,
                     event_id, extra_metadata, is_ai_assisted)
                SELECT evidence_id, entity_id, user_id, source_type, base_weight,
                       raw_content, verified_at, hard_expires_at, session_id,
                       event_id, extra_metadata, is_ai_assisted
                FROM evidence_records_old
            """))
            conn.execute(text("DROP TABLE evidence_records_old"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_er_entity "
                "ON evidence_records (entity_id, verified_at DESC)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_er_user "
                "ON evidence_records (user_id, source_type)"
            ))

        # ── Migration 009: add proficiency_level to profile_entities ──────────
        pe_cols = [r[1] for r in conn.execute(
            text("PRAGMA table_info(profile_entities)")
        ).fetchall()]
        if "proficiency_level" not in pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities ADD COLUMN proficiency_level TEXT"
            ))

    if "confidence_audit_log" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS confidence_audit_log (
                log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id       TEXT NOT NULL REFERENCES profile_entities (entity_id),
                user_id         TEXT NOT NULL,
                old_score       REAL NOT NULL,
                new_score       REAL NOT NULL,
                delta           REAL NOT NULL,
                trigger_source  TEXT NOT NULL,
                evidence_id     TEXT REFERENCES evidence_records (evidence_id),
                session_id      TEXT REFERENCES ariel_sessions (session_id),
                changed_at      TEXT NOT NULL,
                note            TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_cal_entity ON confidence_audit_log (entity_id, changed_at DESC)"))

    if "ariel_gap_queue" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ariel_gap_queue (
                gap_id              TEXT PRIMARY KEY,
                user_id             TEXT NOT NULL,
                entity_id           TEXT NOT NULL REFERENCES profile_entities (entity_id),
                job_id              TEXT,
                current_confidence  REAL NOT NULL,
                required_confidence REAL NOT NULL,
                gap_severity        TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'pending',
                session_id          TEXT REFERENCES ariel_sessions (session_id),
                detected_at         TEXT NOT NULL,
                resolved_at         TEXT
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_agq_user ON ariel_gap_queue (user_id, gap_severity, status)"))

    # ── Migration 004: ariel_probe_log ────────────────────────────────────────
    # Tracks every probe session opened by ArielProbeService so that the
    # 48-hour cooldown can be enforced without re-probing a recently-addressed entity.
    if "ariel_probe_log" not in tables:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ariel_probe_log (
                probe_id        TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                entity_id       TEXT NOT NULL REFERENCES profile_entities (entity_id),
                session_id      TEXT NOT NULL REFERENCES ariel_sessions (session_id),
                outcome         TEXT,
                probed_at       TEXT NOT NULL
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_apl_user_entity "
            "ON ariel_probe_log (user_id, entity_id, probed_at DESC)"
        ))

    # ── Migration 002: add manual_review_required to profile_entities ─────────
    # ALTER TABLE to add the column if the table already exists from migration 001.
    # SQLite supports ADD COLUMN on existing tables; the DEFAULT 0 backfills safely.
    if "profile_entities" in tables:
        existing_pe_cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(profile_entities)"))
        }
        if "manual_review_required" not in existing_pe_cols:
            conn.execute(text(
                "ALTER TABLE profile_entities "
                "ADD COLUMN manual_review_required INTEGER NOT NULL DEFAULT 0"
            ))

    conn.commit()


def init_db() -> None:
    """Create all tables if they don't already exist, then apply any pending migrations."""
    Base.metadata.create_all(ENGINE)
    _migrate()
    # profile_interviews table is created by create_all() on first run;
    # no ALTER TABLE migrations needed since it's a new table.
    with ENGINE.connect() as conn:
        _migrate_confidence_matrix(conn)
