"""
Persistent application store backed by SQLite via SQLAlchemy.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.services.db import ENGINE, ApplicationRow
from models.application import Application, ApplicationStatus


def _to_row(app: Application) -> ApplicationRow:
    return ApplicationRow(
        application_id=app.application_id,
        job_id=app.job_id,
        title=app.title,
        company=app.company,
        ats=app.ats,
        status=app.status.value,
        submitted_at=app.submitted_at,
        last_update=app.last_update,
        score=app.score,
        cover_letter=app.cover_letter,
        reason=app.reason,
    )


def _from_row(row: ApplicationRow) -> Application:
    return Application(
        application_id=row.application_id,
        job_id=row.job_id,
        title=row.title,
        company=row.company,
        ats=row.ats,
        status=ApplicationStatus(row.status),
        submitted_at=row.submitted_at,
        last_update=row.last_update,
        score=row.score,
        cover_letter=row.cover_letter,
        reason=row.reason,
    )


def save(app: Application) -> None:
    with Session(ENGINE) as session:
        session.merge(_to_row(app))
        session.commit()


def get_all(user_id: str = "default") -> list[Application]:
    """Return all applications for user_id, ordered by most recently submitted first."""
    with Session(ENGINE) as session:
        rows = (
            session.query(ApplicationRow)
            .filter(ApplicationRow.user_id == user_id)
            .order_by(ApplicationRow.submitted_at.desc())
            .all()
        )
        return [_from_row(r) for r in rows]


def has_application(job_id: str, user_id: str = "default") -> bool:
    """Return True if user_id already has an application row for job_id."""
    with Session(ENGINE) as session:
        return (
            session.query(ApplicationRow)
            .filter(
                ApplicationRow.job_id  == job_id,
                ApplicationRow.user_id == user_id,
            )
            .count() > 0
        )
