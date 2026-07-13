"""SQLAlchemy models for the LinkedIn job ingestion pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.ingestion.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """A LinkedIn job posting tracked by the ingestion pipeline."""

    __tablename__ = "ingestion_jobs"

    # 9-10 digit LinkedIn job ID, used verbatim as the primary key.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    title: Mapped[Optional[str]] = mapped_column(String(500))
    company_name: Mapped[Optional[str]] = mapped_column(String(500))
    location: Mapped[Optional[str]] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)
    experience_level: Mapped[Optional[str]] = mapped_column(String(200))
    work_type: Mapped[Optional[str]] = mapped_column(String(200))
    job_classification: Mapped[Optional[str]] = mapped_column(String(500))
    apply_url: Mapped[Optional[str]] = mapped_column(String(1000))

    applications_count: Mapped[Optional[str]] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)

    system_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    linkedin_posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Job id={self.id} status={self.status!r} title={self.title!r}>"
