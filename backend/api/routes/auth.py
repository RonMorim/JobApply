"""
Auth utility routes.

POST /api/auth/migrate-legacy-data
    One-time migration: reassigns all SQLite rows and the on-disk profile file
    that were created under user_id='default' (the legacy single-user mode) to
    the calling user's real Supabase user_id.

    Safety rules
    ────────────
    1. Idempotent — if the calling user already owns rows in any table the
       endpoint returns {status: "already_done"} without touching the database.
    2. Exclusive — only rows owned by the literal string 'default' are moved;
       rows belonging to any other real user_id are never touched.
    3. File copy — if data/master_profile.json exists it is copied (not moved)
       to data/users/{user_id}/profile.json.  The legacy file is left in place
       so a server restart doesn't break anything before the next deploy.
    4. Counts — returns the number of rows migrated per table so the frontend
       can decide whether a reload is worthwhile.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from backend.api.deps import CurrentUser, get_current_user
from backend.services.db import ENGINE, ApplicationRow, JobRow, ProfileInterviewRow
from backend.services.active_user import set_active_user_id

logger = logging.getLogger(__name__)
router = APIRouter()

# Paths used by the legacy single-user profile store
_PROJECT_ROOT   = Path(__file__).resolve().parents[3]   # repo root
_LEGACY_PROFILE = _PROJECT_ROOT / "backend" / "data" / "master_profile.json"
_USERS_DIR      = _PROJECT_ROOT / "backend" / "data" / "users"


# ── Response model ────────────────────────────────────────────────────────────

class MigrationResult(BaseModel):
    status:         str   # "ok" | "already_done" | "nothing_to_migrate"
    jobs:           int = 0
    applications:   int = 0
    interviews:     int = 0
    profile_file:   bool = False
    message:        str = ""


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/migrate-legacy-data", response_model=MigrationResult)
async def migrate_legacy_data(
    user: CurrentUser = Depends(get_current_user),
) -> MigrationResult:
    """
    Reassign all 'default' user_id rows in every table to the authenticated
    caller's real user_id.  Safe to call multiple times — returns immediately
    if the user already has data or there is nothing to migrate.
    """
    uid = user.user_id

    with DBSession(ENGINE) as db:
        # ── Guard 1: already migrated ────────────────────────────────────────
        # If this user already owns rows in ANY table their data is present and
        # the migration was already performed (or they registered fresh after
        # the multi-tenant rollout).  Don't touch anything.
        already_has_jobs   = db.query(JobRow)              .filter(JobRow.user_id              == uid).count()
        already_has_apps   = db.query(ApplicationRow)      .filter(ApplicationRow.user_id      == uid).count()
        already_has_ivws   = db.query(ProfileInterviewRow) .filter(ProfileInterviewRow.user_id == uid).count()

        if already_has_jobs or already_has_apps or already_has_ivws:
            logger.info(
                "[auth/migrate] user=%s already owns data — skipping "
                "(jobs=%d apps=%d interviews=%d)",
                uid, already_has_jobs, already_has_apps, already_has_ivws,
            )
            # Even on the fast-path: register this user so the next discovery
            # cycle writes new jobs to their feed, not to 'default'.
            set_active_user_id(uid)
            return MigrationResult(
                status  = "already_done",
                message = "User already owns data; no migration needed.",
            )

        # ── Guard 2: nothing to migrate ───────────────────────────────────────
        legacy_jobs  = db.query(JobRow)             .filter(JobRow.user_id              == "default").count()
        legacy_apps  = db.query(ApplicationRow)     .filter(ApplicationRow.user_id      == "default").count()
        legacy_ivws  = db.query(ProfileInterviewRow).filter(ProfileInterviewRow.user_id == "default").count()

        if not (legacy_jobs or legacy_apps or legacy_ivws):
            logger.info("[auth/migrate] user=%s — no legacy data to migrate", uid)
            # New user: register them so future scrapes write to their feed.
            set_active_user_id(uid)
            return MigrationResult(
                status  = "nothing_to_migrate",
                message = "No legacy data found under user_id='default'.",
            )

        # ── Migrate ───────────────────────────────────────────────────────────
        migrated_jobs = (
            db.query(JobRow)
            .filter(JobRow.user_id == "default")
            .update({"user_id": uid}, synchronize_session="fetch")
        )
        migrated_apps = (
            db.query(ApplicationRow)
            .filter(ApplicationRow.user_id == "default")
            .update({"user_id": uid}, synchronize_session="fetch")
        )
        migrated_ivws = (
            db.query(ProfileInterviewRow)
            .filter(ProfileInterviewRow.user_id == "default")
            .update({"user_id": uid}, synchronize_session="fetch")
        )
        db.commit()

        logger.info(
            "[auth/migrate] Migrated to user=%s — jobs=%d apps=%d interviews=%d",
            uid, migrated_jobs, migrated_apps, migrated_ivws,
        )

    # ── Register as active user so next scrape cycle writes to this feed ──────
    set_active_user_id(uid)

    # ── Profile file ──────────────────────────────────────────────────────────
    profile_copied = False
    if _LEGACY_PROFILE.exists():
        dest = _USERS_DIR / uid / "profile.json"
        if not dest.exists():
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_LEGACY_PROFILE, dest)
                profile_copied = True
                logger.info("[auth/migrate] Copied master_profile.json → %s", dest)
            except Exception as exc:
                logger.warning("[auth/migrate] Profile file copy failed: %s", exc)

    return MigrationResult(
        status        = "ok",
        jobs          = migrated_jobs,
        applications  = migrated_apps,
        interviews    = migrated_ivws,
        profile_file  = profile_copied,
        message       = (
            f"Migrated {migrated_jobs} job(s), {migrated_apps} application(s), "
            f"{migrated_ivws} interview session(s)"
            + (" and profile file" if profile_copied else "")
            + f" to user {uid}."
        ),
    )
