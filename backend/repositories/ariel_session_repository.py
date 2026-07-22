"""Repository for the ariel_sessions table.

Consolidates the raw ENGINE.begin()/text() CRUD for Ariel conversation
sessions, previously split between the raw-SQL transcript read/write in
backend/api/routes/ariel.py and the session lifecycle helpers
(open_session/close_session) in backend/services/profile_update_service.py.

Every function accepts an optional `engine` override (falling back to the
shared ENGINE, resolved at call time) so ProfileUpdateService — which is
constructed with an injectable engine for testability — can route session
lifecycle writes through its own `self._engine` instead of always hitting
the production database.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.core.database import ENGINE


def create_session(
    *,
    session_id: str,
    user_id: str,
    session_type: str,
    started_at: str,
    target_job_id: Optional[str] = None,
    target_entities: Optional[list[str]] = None,
    ariel_goal: Optional[str] = None,
    engine: Optional[Engine] = None,
) -> None:
    eng = engine or ENGINE
    with eng.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ariel_sessions
                    (session_id, user_id, session_type,
                     target_job_id, target_entities, ariel_goal,
                     status, started_at)
                VALUES
                    (:sid, :uid, :stype,
                     :jid, :ents, :goal,
                     'active', :now)
            """),
            {
                "sid":   session_id,
                "uid":   user_id,
                "stype": session_type,
                "jid":   target_job_id,
                "ents":  json.dumps(target_entities or []),
                "goal":  ariel_goal,
                "now":   started_at,
            },
        )


def update_status(
    session_id: str,
    status: str,
    ended_at: str,
    engine: Optional[Engine] = None,
) -> None:
    eng = engine or ENGINE
    with eng.begin() as conn:
        conn.execute(
            text("""
                UPDATE ariel_sessions
                SET    status = :status, ended_at = :now
                WHERE  session_id = :sid
            """),
            {"status": status, "now": ended_at, "sid": session_id},
        )


def get_transcript(
    session_id: str,
    user_id: str,
    engine: Optional[Engine] = None,
) -> Optional[dict]:
    """Return the session's transcript dict, or None if no such session (scoped to user_id)."""
    eng = engine or ENGINE
    with eng.begin() as conn:
        row = conn.execute(
            text("SELECT transcript_json FROM ariel_sessions WHERE session_id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user_id},
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0] or "{}")


def save_transcript(
    session_id: str,
    user_id: str,
    transcript: dict,
    engine: Optional[Engine] = None,
) -> None:
    eng = engine or ENGINE
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE ariel_sessions SET transcript_json = :tj WHERE session_id = :sid AND user_id = :uid"),
            {"tj": json.dumps(transcript), "sid": session_id, "uid": user_id},
        )
