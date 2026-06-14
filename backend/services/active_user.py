"""
Active-user registry for background pipeline tasks.

The discovery loop and ScraperManager run globally (not per-request).
This module provides a lightweight file-backed registry so the pipeline
always writes newly scraped jobs to the correct authenticated user_id.

set_active_user_id() is called by the migration endpoint the first time a
user logs in and completes their data migration.  From that point on, every
background scrape cycle writes jobs owned by that user.

Falls back to 'default' when no user has registered yet (pre-auth state),
which keeps the pipeline functional for local development even before the
first login.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Stored next to the main.py entry-point so it survives process restarts.
_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "active_user.json"


def get_active_user_id() -> str:
    """
    Return the user_id that should own all background-scraped jobs.

    Reads from disk on every call so the discovery loop picks up a newly
    registered user_id on the very next cycle without requiring a restart.

    Returns 'default' if:
      • The state file does not exist yet (no user has logged in)
      • The file is corrupt / unreadable
      • The stored user_id is blank
    """
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        uid  = (data.get("user_id") or "").strip()
        return uid if uid else "default"
    except FileNotFoundError:
        return "default"
    except Exception as exc:
        logger.warning("[active_user] Could not read %s: %s", _STATE_FILE, exc)
        return "default"


def set_active_user_id(user_id: str) -> None:
    """
    Persist the active user_id so subsequent discovery cycles own their jobs.

    Called by the /api/auth/migrate-legacy-data endpoint after a successful
    migration — meaning every new background-scraped job from this point on
    is immediately visible in the authenticated user's feed.
    """
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps({"user_id": user_id}, indent=2),
            encoding="utf-8",
        )
        logger.info("[active_user] Active user_id set → %r", user_id)
    except Exception as exc:
        logger.error("[active_user] Failed to persist active_user_id=%r: %s", user_id, exc)
