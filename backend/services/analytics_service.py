"""
Analytics service — aggregate dashboard KPIs for one user.

compute_overview(user_id) -> dict
  {
    "average_match_score": float,  # AVG(JobRow.match_score) across scored jobs, 1 decimal
    "top_strengths":       [{"name": str, "confidence_score": float}],  # top 5 skills
    "tailored_cv_count":   int,    # JobRow rows with a tailored_cv on file
  }

Value-driven by design: every field ties directly back to what the user's
Master Profile and ATS scoring pipeline actually know about them, instead of
generic activity counters (jobs scanned, actions taken) that say nothing
about fit or skill strength.

Tenant isolation
----------------
Every query in this module filters by user_id == user_id. There is no code
path that reads another tenant's rows — the user_id comes exclusively from
the verified JWT (CurrentUser) at the route layer, never from the client
payload.
"""
from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.services.db import ENGINE, JobRow, ProfileEntityRow

logger = logging.getLogger(__name__)

_TOP_STRENGTHS_LIMIT = 5


def compute_overview(user_id: str) -> dict:
    """Return the Overview KPI values for `user_id` (and only `user_id`)."""
    with Session(ENGINE) as db:
        avg_score_raw = (
            db.query(func.avg(JobRow.match_score))
            .filter(JobRow.user_id == user_id, JobRow.match_score > 0)
            .scalar()
        )
        average_match_score = round(float(avg_score_raw), 1) if avg_score_raw else 0.0

        tailored_cv_count = int(
            db.query(func.count(JobRow.job_id))
            .filter(JobRow.user_id == user_id, JobRow.tailored_cv.isnot(None))
            .scalar()
            or 0
        )

        strength_rows = (
            db.query(ProfileEntityRow.name, ProfileEntityRow.confidence_score)
            .filter(
                ProfileEntityRow.user_id == user_id,
                ProfileEntityRow.entity_type == "skill",
            )
            .order_by(ProfileEntityRow.confidence_score.desc())
            .limit(_TOP_STRENGTHS_LIMIT)
            .all()
        )
        top_strengths = [
            {"name": name, "confidence_score": round(float(score), 1)}
            for name, score in strength_rows
        ]

    logger.info(
        "[analytics] overview user=%s avg_match=%.1f tailored_cvs=%d strengths=%d",
        user_id, average_match_score, tailored_cv_count, len(top_strengths),
    )

    return {
        "average_match_score": average_match_score,
        "top_strengths":       top_strengths,
        "tailored_cv_count":   tailored_cv_count,
    }
