"""
Analytics service — aggregate dashboard KPIs for one user.

compute_overview(user_id) -> dict
  {
    "total_jobs_scanned":  int,   # all JobRow rows owned by the user
    "jobs_scanned_today":  int,   # subset created since UTC midnight
    "high_matches":        int,   # match_score > 85
    "actions_taken":       int,   # outreach generated OR CV tailored
  }

Tenant isolation
----------------
Every query in this module filters by JobRow.user_id == user_id. There is no
code path that reads another tenant's rows — the user_id comes exclusively
from the verified JWT (CurrentUser) at the route layer, never from the client
payload.

All metrics are computed as SQL COUNTs (no row materialisation), so the
endpoint stays cheap even for large feeds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from services.db import ENGINE, JobRow

logger = logging.getLogger(__name__)

_HIGH_MATCH_THRESHOLD = 85.0


def compute_overview(user_id: str) -> dict:
    """Return the Overview KPI counters for `user_id` (and only `user_id`)."""
    today_start = (
        datetime.now(timezone.utc)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
    )

    with Session(ENGINE) as db:
        def _count(*filters) -> int:
            return int(
                db.query(func.count(JobRow.job_id))
                .filter(JobRow.user_id == user_id, *filters)
                .scalar()
                or 0
            )

        total_jobs_scanned = _count()

        # created_at is stored as ISO-8601 UTC strings, so lexicographic
        # comparison against the midnight boundary is chronologically correct.
        jobs_scanned_today = _count(
            JobRow.created_at.isnot(None),
            JobRow.created_at >= today_start,
        )

        high_matches = _count(JobRow.match_score > _HIGH_MATCH_THRESHOLD)

        actions_taken = _count(
            or_(
                JobRow.outreach_text.isnot(None),   # outreach generated
                JobRow.tailored_cv.isnot(None),     # CV tailored
            )
        )

    logger.info(
        "[analytics] overview user=%s total=%d today=%d high=%d actions=%d",
        user_id, total_jobs_scanned, jobs_scanned_today, high_matches, actions_taken,
    )

    return {
        "total_jobs_scanned": total_jobs_scanned,
        "jobs_scanned_today": jobs_scanned_today,
        "high_matches":       high_matches,
        "actions_taken":      actions_taken,
    }
