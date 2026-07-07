"""
Unit tests — GET /api/profile/{user_id}/trust-score
=====================================================

Coverage:
  1. compute_profile_trust_score()
       - empty profile  →  0.0
       - single-category profile (all skills)
       - mixed-category profile with known weights (weighted geometric "OR"
         combination — see Phase 28 fix in profile_update_service.py)
       - fixed (never renormalised) weights when one category is absent
       - monotonicity regression: adding new (low-confidence) data, whether
         to an existing category or a brand-new one, must never lower the
         overall score

  2. HTTP endpoint  (FastAPI TestClient, auth dependency overridden)
       - 200 with correct JSON structure for a user with 2 entities
         (one 'verified' skill, one 'unverified' skill)
       - overall_trust_score, category_averages, trust_breakdown present
       - manual_review_required mapped to bool
       - 403 when caller requests a different user's data
       - 200 with empty lists for a user with 0 entities

All tests run against an isolated in-memory SQLite database so the real
jobs.db is never touched.

Running
-------
From the project root (JobApply_Venture/):

    backend/.venv/bin/pytest backend/tests/test_profile_trust.py -v

Or, if pytest is on the active PATH:

    pytest backend/tests/test_profile_trust.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Shared in-memory SQLite engine (isolated per test session)
# ---------------------------------------------------------------------------
# StaticPool is REQUIRED for sqlite:///:memory:. Without it, SQLAlchemy's
# default QueuePool gives every new connection its own in-memory database,
# so tables created during setup are invisible to the route's Session.
# StaticPool forces all checkouts to reuse the single underlying connection,
# keeping one consistent in-memory database throughout the entire test run.

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def _setup_schema() -> None:
    """Create all tables required by the confidence matrix in the test engine."""
    from backend.services.db import Base

    # Create the standard ORM-mapped tables (jobs, applications, etc.)
    Base.metadata.create_all(_TEST_ENGINE)

    # Create the confidence-matrix tables that are managed by raw SQL migrations.
    with _TEST_ENGINE.begin() as conn:
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
                updated_at             TEXT NOT NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS evidence_records (
                evidence_id     TEXT PRIMARY KEY,
                entity_id       TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                source_type     TEXT NOT NULL,
                base_weight     REAL NOT NULL,
                raw_content     TEXT,
                verified_at     TEXT NOT NULL,
                hard_expires_at TEXT,
                session_id      TEXT,
                event_id        TEXT,
                extra_metadata  TEXT
            )
        """))

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


# Run schema setup once when the module loads.
_setup_schema()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_entity(
    conn,
    *,
    user_id: str,
    entity_type: str,
    name: str,
    confidence_score: float,
    manual_review_required: int = 0,
) -> str:
    """Insert a profile_entities row and return its entity_id."""
    entity_id = _uid()
    now = _now()
    conn.execute(
        text("""
            INSERT INTO profile_entities
                (entity_id, user_id, entity_type, name, normalized_name,
                 confidence_score, verification_status, manual_review_required,
                 created_at, updated_at)
            VALUES
                (:eid, :uid, :etype, :name, :norm,
                 :score, :status, :manual,
                 :now, :now)
        """),
        {
            "eid":    entity_id,
            "uid":    user_id,
            "etype":  entity_type,
            "name":   name,
            "norm":   name.lower().replace(" ", "_"),
            "score":  confidence_score,
            "status": "verified" if confidence_score >= 75 else "unverified",
            "manual": manual_review_required,
            "now":    now,
        },
    )
    return entity_id


def _insert_evidence(
    conn,
    *,
    entity_id: str,
    user_id: str,
    source_type: str = "cv_parse",
    base_weight: float = 25.0,
    raw_content: str = "",
    hard_expires_at: str | None = None,
) -> str:
    """Insert an evidence_records row and return its evidence_id."""
    ev_id = _uid()
    conn.execute(
        text("""
            INSERT INTO evidence_records
                (evidence_id, entity_id, user_id, source_type,
                 base_weight, raw_content, verified_at, hard_expires_at)
            VALUES
                (:evid, :eid, :uid, :src, :w, :raw, :now, :exp)
        """),
        {
            "evid": ev_id,
            "eid":  entity_id,
            "uid":  user_id,
            "src":  source_type,
            "w":    base_weight,
            "raw":  raw_content,
            "now":  _now(),
            "exp":  hard_expires_at,
        },
    )
    return ev_id


# ---------------------------------------------------------------------------
# Unit tests: compute_profile_trust_score
# ---------------------------------------------------------------------------

class TestComputeProfileTrustScore:
    """Direct unit tests for ProfileUpdateService.compute_profile_trust_score."""

    def _service(self):
        from backend.services.profile_update_service import ProfileUpdateService
        return ProfileUpdateService(_TEST_ENGINE)

    def test_empty_profile_returns_zero(self):
        """A user with no entities must return 0.0 — never a crash."""
        svc = self._service()
        score = svc.compute_profile_trust_score("nonexistent-user-" + _uid())
        assert score == 0.0

    def test_single_skill_entity(self):
        """
        One skill entity → weighted geometric ("OR") combination, not a raw
        average. skill_trait's own group_score = geo_combine([80]) = 80.0,
        but experience/domain are empty and each still carries its FIXED
        weight as an exponent (never renormalised away), so a lone category
        caps out below its raw score:

          complement = (1 − 80/100)^0.40 × (1 − 0)^0.40 × (1 − 0)^0.20
                     = 0.2^0.40 × 1 × 1 ≈ 0.525263
          overall    = 100 × (1 − 0.525263) ≈ 47.5
        """
        uid = "test-single-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Python", confidence_score=80.0)

        svc = self._service()
        score = svc.compute_profile_trust_score(uid)
        assert score == pytest.approx(47.5, abs=0.1)

    def test_weighted_combination_skill_and_experience(self):
        """
        Two groups (skill + experience), each weight 0.40; domain empty.
        group_score_skill = geo_combine([60]) = 60.0
        group_score_exp   = geo_combine([80]) = 80.0

          complement = (1 − 0.60)^0.40 × (1 − 0.80)^0.40 × (1 − 0)^0.20
                     = 0.4^0.40 × 0.2^0.40 × 1 ≈ 0.363936
          overall    = 100 × (1 − 0.363936) ≈ 63.6
        """
        uid = "test-weighted-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Roadmap Planning", confidence_score=60.0)
            _insert_entity(conn, user_id=uid, entity_type="experience",
                           name="Team Lead", confidence_score=80.0)

        svc = self._service()
        score = svc.compute_profile_trust_score(uid)
        assert score == pytest.approx(63.6, abs=0.1)

    def test_all_three_groups_full_weights(self):
        """
        All three groups present with weights (0.4, 0.4, 0.2). domain = 100.0
        makes its term (1 − 1.0)^0.20 == 0, zeroing the whole complement:

          complement = (1 − 0.50)^0.40 × (1 − 0.75)^0.40 × (1 − 1.00)^0.20
                     = ... × 0.0 = 0.0
          overall    = 100 × (1 − 0) = 100.0
        """
        uid = "test-full-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Data Analysis", confidence_score=50.0)
            _insert_entity(conn, user_id=uid, entity_type="experience",
                           name="Senior PM", confidence_score=75.0)
            _insert_entity(conn, user_id=uid, entity_type="domain",
                           name="FinTech", confidence_score=100.0)

        svc = self._service()
        score = svc.compute_profile_trust_score(uid)
        assert score == pytest.approx(100.0, abs=0.1)

    def test_trait_grouped_with_skill(self):
        """
        Trait entities count toward the skill_trait bucket, combined via
        geo_combine (not averaged): geo_combine([40, 60])
          = 100 × (1 − (1−0.40)×(1−0.60)) = 100 × (1 − 0.24) = 76.0
        Only skill_trait is populated, so its weight (0.40) still applies as
        an exponent (experience/domain empty → neutral terms):

          complement = (1 − 0.76)^0.40 × 1 × 1 = 0.24^0.40 ≈ 0.565345
          overall    = 100 × (1 − 0.565345) ≈ 43.5
        """
        uid = "test-trait-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Negotiation", confidence_score=40.0)
            _insert_entity(conn, user_id=uid, entity_type="trait",
                           name="Empathy", confidence_score=60.0)

        svc = self._service()
        score = svc.compute_profile_trust_score(uid)
        assert score == pytest.approx(43.5, abs=0.1)

    def test_score_clamped_to_100(self):
        """Score is always ≤ 100 even if somehow entities carry inflated values."""
        uid = "test-clamp-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Inflated", confidence_score=150.0)

        svc = self._service()
        score = svc.compute_profile_trust_score(uid)
        assert score <= 100.0

    # -----------------------------------------------------------------------
    # Regression: adding new (low-confidence) data must never lower the score
    # -----------------------------------------------------------------------
    # This is the Phase 28 bug report: a user chatted with Ariel, added valid
    # new profile data, and watched their System Confidence Score drop
    # (18 → 16). The old implementation averaged raw confidence_score per
    # category, so a freshly-created entity (which always starts near 0 —
    # see _upsert_entity) dragged the category mean down the instant it was
    # added. The new geometric ("OR") combination is monotonically
    # non-decreasing in every entity score, so this must never happen again.

    def test_adding_low_confidence_entity_to_existing_category_never_lowers_score(self):
        """Adding a second, low-scoring skill must not lower the overall score."""
        uid = "test-mono-existing-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Product Strategy", confidence_score=55.0)

        svc = self._service()
        before = svc.compute_profile_trust_score(uid)

        # Simulate Ariel extracting a brand-new, still-unverified skill —
        # freshly created entities start with a low confidence_score.
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Stakeholder Mapping", confidence_score=7.5)

        after = svc.compute_profile_trust_score(uid)
        assert after >= before

    def test_adding_first_entity_to_new_category_never_lowers_score(self):
        """
        A user's FIRST-ever entity in a previously-empty category (e.g. their
        first "domain" claim) must not lower the overall score either — this
        was the second monotonicity hole in the old renormalised-weight
        approach (a new category's weight share was carved out of the
        existing categories' share the instant it gained data).
        """
        uid = "test-mono-new-category-" + _uid()
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Data Analysis", confidence_score=50.0)
            _insert_entity(conn, user_id=uid, entity_type="experience",
                           name="Senior PM", confidence_score=75.0)

        svc = self._service()
        before = svc.compute_profile_trust_score(uid)

        # First-ever domain entity — freshly created, low confidence.
        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="domain",
                           name="FinTech", confidence_score=7.5)

        after = svc.compute_profile_trust_score(uid)
        assert after >= before


# ---------------------------------------------------------------------------
# HTTP integration tests: GET /api/profile/{user_id}/trust-score
# ---------------------------------------------------------------------------
#
# Strategy
# --------
# We override the get_current_user dependency so the test runner doesn't need
# a real JWT.  The override returns a CurrentUser whose user_id we control.
# The endpoint is wired to ENGINE which we monkey-patch to point at _TEST_ENGINE
# for the duration of the test module.

class TestTrustScoreEndpoint:
    """
    FastAPI TestClient tests exercising the full HTTP stack.

    These tests patch:
      • backend.services.db.ENGINE          →  _TEST_ENGINE (in-memory SQLite)
      • backend.api.deps.get_current_user   →  returns a synthetic CurrentUser
    """

    @pytest.fixture(autouse=True)
    def _patch_engine(self, monkeypatch):
        """Replace the shared ENGINE with the test-scoped in-memory engine."""
        import backend.services.db as _db_module
        import backend.api.routes.profile as _profile_module

        monkeypatch.setattr(_db_module, "ENGINE", _TEST_ENGINE)
        monkeypatch.setattr(_profile_module, "ENGINE", _TEST_ENGINE)

    def _make_client(self, caller_user_id: str) -> TestClient:
        """Return a TestClient whose auth dependency returns caller_user_id."""
        from backend.main import app
        from backend.api.deps import CurrentUser, get_current_user

        def _override():
            return CurrentUser(user_id=caller_user_id, email="test@example.com")

        app.dependency_overrides[get_current_user] = _override
        client = TestClient(app, raise_server_exceptions=False)
        return client

    def _teardown_client(self, client: TestClient) -> None:
        from backend.main import app
        from backend.api.deps import get_current_user
        app.dependency_overrides.pop(get_current_user, None)

    # ── Test: canonical 2-entity case ────────────────────────────────────────

    def test_two_entities_correct_structure(self):
        """
        Core acceptance test per spec:
          • 2 entities: one 'verified' (confidence 80), one 'unverified' (confidence 20)
          • Response contains correct JSON structure
          • overall_trust_score, category_averages, trust_breakdown all present
          • manual_review_required is a bool
        """
        uid = "http-test-" + _uid()
        ev_id_a = ev_id_b = None

        with _TEST_ENGINE.begin() as conn:
            eid_a = _insert_entity(conn, user_id=uid, entity_type="skill",
                                   name="Product Vision", confidence_score=80.0)
            ev_id_a = _insert_evidence(
                conn, entity_id=eid_a, user_id=uid,
                source_type="conversation_star", base_weight=72.0,
                raw_content="Led a 6-month roadmap rebuild for a 40-person engineering org.",
            )

            eid_b = _insert_entity(conn, user_id=uid, entity_type="skill",
                                   name="SQL", confidence_score=20.0)
            ev_id_b = _insert_evidence(
                conn, entity_id=eid_b, user_id=uid,
                source_type="cv_parse", base_weight=25.0,
                raw_content="Wrote complex SQL queries for BI reporting.",
            )

        client = self._make_client(uid)
        try:
            resp = client.get(f"/api/profile/{uid}/trust-score")
        finally:
            self._teardown_client(client)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        # ── Top-level keys ────────────────────────────────────────────────────
        assert body["user_id"] == uid
        assert "overall_trust_score" in body
        assert "category_averages" in body
        assert "entities" in body
        assert "fetched_at" in body

        # ── overall_trust_score: weighted geometric ("OR") combination.
        #    group_score_skill = geo_combine([80, 20])
        #      = 100 × (1 − (1−0.80)×(1−0.20)) = 100 × (1 − 0.16) = 84.0
        #    only skill_trait populated → its 0.40 weight applies as an
        #    exponent (experience/domain empty → neutral terms):
        #      complement = (1 − 0.84)^0.40 ≈ 0.4805
        #      overall    = 100 × (1 − 0.4805) ≈ 52.0
        # (category_averages below is a SEPARATE plain-average field used
        #  only for display — e.g. the radar chart — and is unaffected.)
        assert body["overall_trust_score"] == pytest.approx(52.0, abs=0.2)

        # ── category_averages ────────────────────────────────────────────────
        cat = body["category_averages"]
        assert set(cat.keys()) == {"skill", "trait", "domain", "experience"}
        assert cat["skill"] == pytest.approx(50.0, abs=0.2)   # (80+20)/2
        assert cat["trait"]      == 0.0
        assert cat["domain"]     == 0.0
        assert cat["experience"] == 0.0

        # ── entities ─────────────────────────────────────────────────────────
        assert len(body["entities"]) == 2

        # Entities sorted confidence DESC → [80.0, 20.0]
        high, low = body["entities"][0], body["entities"][1]

        assert high["name"]             == "Product Vision"
        assert high["confidence_score"] == pytest.approx(80.0, abs=0.1)
        assert high["entity_type"]      == "skill"
        assert isinstance(high["manual_review_required"], bool)
        assert high["manual_review_required"] is False

        assert low["name"]             == "SQL"
        assert low["confidence_score"] == pytest.approx(20.0, abs=0.1)

        # ── trust_breakdown ──────────────────────────────────────────────────
        tb_high = high["trust_breakdown"]
        assert len(tb_high) == 1
        assert tb_high[0]["source_type"]  == "conversation_star"
        assert tb_high[0]["source_label"] == "STAR Behavioral Probe"
        assert tb_high[0]["evidence_id"]  == ev_id_a
        assert "verified_at" in tb_high[0]
        assert "raw_content" in tb_high[0]
        assert "base_weight" in tb_high[0]

        tb_low = low["trust_breakdown"]
        assert len(tb_low) == 1
        assert tb_low[0]["source_type"]  == "cv_parse"
        assert tb_low[0]["source_label"] == "CV Parse"
        assert tb_low[0]["evidence_id"]  == ev_id_b

    # ── Test: zero-entity guard ───────────────────────────────────────────────

    def test_empty_profile_returns_200_not_500(self):
        """A user with 0 entities must return HTTP 200 with empty lists."""
        uid = "http-empty-" + _uid()

        client = self._make_client(uid)
        try:
            resp = client.get(f"/api/profile/{uid}/trust-score")
        finally:
            self._teardown_client(client)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["overall_trust_score"] == 0.0
        assert body["entities"] == []
        cat = body["category_averages"]
        assert cat["skill"] == 0.0
        assert cat["experience"] == 0.0

    # ── Test: 403 when accessing another user's data ─────────────────────────

    def test_cross_user_access_returns_403(self):
        """Authenticated as user A, requesting user B's trust score → 403."""
        caller_uid = "caller-" + _uid()
        target_uid = "target-" + _uid()

        client = self._make_client(caller_uid)
        try:
            resp = client.get(f"/api/profile/{target_uid}/trust-score")
        finally:
            self._teardown_client(client)

        assert resp.status_code == 403

    # ── Test: hard-expired evidence excluded ─────────────────────────────────

    def test_hard_expired_evidence_excluded_from_breakdown(self):
        """Evidence rows with hard_expires_at in the past must not appear."""
        uid = "http-expiry-" + _uid()
        past_iso = "2000-01-01T00:00:00+00:00"   # safely in the past

        with _TEST_ENGINE.begin() as conn:
            eid = _insert_entity(conn, user_id=uid, entity_type="experience",
                                 name="Engineering Director", confidence_score=90.0)
            # Valid evidence
            _insert_evidence(conn, entity_id=eid, user_id=uid,
                             source_type="certification", base_weight=55.0,
                             raw_content="Active cert.")
            # Hard-expired evidence — must not appear in breakdown
            _insert_evidence(conn, entity_id=eid, user_id=uid,
                             source_type="certification", base_weight=55.0,
                             raw_content="Expired cert.",
                             hard_expires_at=past_iso)

        client = self._make_client(uid)
        try:
            resp = client.get(f"/api/profile/{uid}/trust-score")
        finally:
            self._teardown_client(client)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entities"]) == 1
        # Only the non-expired evidence should appear
        breakdown = body["entities"][0]["trust_breakdown"]
        assert len(breakdown) == 1
        assert breakdown[0]["raw_content"] == "Active cert."

    # ── Test: manual_review_required bool casting ─────────────────────────────

    def test_manual_review_required_is_bool(self):
        """The INTEGER 0/1 stored in SQLite must be returned as a JSON bool."""
        uid = "http-manual-" + _uid()

        with _TEST_ENGINE.begin() as conn:
            _insert_entity(conn, user_id=uid, entity_type="skill",
                           name="Leadership", confidence_score=15.0,
                           manual_review_required=1)

        client = self._make_client(uid)
        try:
            resp = client.get(f"/api/profile/{uid}/trust-score")
        finally:
            self._teardown_client(client)

        assert resp.status_code == 200
        entity = resp.json()["entities"][0]
        # Must be a proper Python bool in JSON, not the integer 1
        assert entity["manual_review_required"] is True
        assert type(entity["manual_review_required"]) is bool
