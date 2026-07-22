"""Repository for the recruiter_reply_drafts table.

Consolidates the single insert previously inlined in
backend/services/orchestrator.py's draft_recruiter_reply.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.database import ENGINE
from backend.models.application import RecruiterReplyDraftRow


def insert(
    *,
    draft_id: str,
    user_id: str,
    job_id: str,
    email_excerpt: str,
    draft_text: str,
    status: str,
    created_at: str,
) -> None:
    with Session(ENGINE) as session:
        session.add(RecruiterReplyDraftRow(
            draft_id      = draft_id,
            user_id       = user_id,
            job_id        = job_id,
            email_excerpt = email_excerpt,
            draft_text    = draft_text,
            status        = status,
            created_at    = created_at,
        ))
        session.commit()
