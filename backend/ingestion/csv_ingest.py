"""CSV ingestion: normalizes LinkedIn job URLs and upserts jobs.csv into Postgres.

Behavior:
  - Extract the 9-10 digit numeric job ID out of each row's `job_url`.
  - Reconstruct a clean canonical URL: https://www.linkedin.com/jobs/view/{id}/
  - Upsert each row: insert new jobs, or update `applications_count` and
    reset `status` to 'open' for existing ones.
  - Any job currently 'open' in the DB but absent from this CSV run is
    marked 'closed' (it fell off LinkedIn's listing).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.db import get_session
from backend.ingestion.models import Job

logger = logging.getLogger(__name__)

# LinkedIn numeric job IDs are 9-10 digits. Matches both
# ".../jobs/view/1234567890/..." and "...currentJobId=1234567890..." forms.
_JOB_ID_RE = re.compile(r"(\d{9,10})")

LINKEDIN_JOB_URL_TEMPLATE = "https://www.linkedin.com/jobs/view/{job_id}/"


def extract_job_id(job_url: str) -> str | None:
    """Pull the 9-10 digit numeric LinkedIn job ID out of a raw job URL."""
    if not isinstance(job_url, str):
        return None
    match = _JOB_ID_RE.search(job_url)
    return match.group(1) if match else None


def normalize_job_url(job_id: str) -> str:
    return LINKEDIN_JOB_URL_TEMPLATE.format(job_id=job_id)


def _load_and_normalize_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    if "job_url" not in df.columns:
        raise ValueError("jobs.csv is missing the required 'job_url' column")

    df["job_id"] = df["job_url"].apply(extract_job_id)
    dropped = df["job_id"].isna().sum()
    if dropped:
        logger.warning("Dropping %d rows with unparseable job_url", dropped)
    df = df.dropna(subset=["job_id"]).copy()
    df["job_id"] = df["job_id"].astype(int)
    df["apply_url"] = df["job_id"].apply(lambda jid: normalize_job_url(str(jid)))

    # If the CSV has duplicate job IDs (e.g. re-scraped same posting twice),
    # keep the last occurrence.
    df = df.drop_duplicates(subset=["job_id"], keep="last")
    return df


async def _upsert_jobs(session: AsyncSession, df: pd.DataFrame) -> list[int]:
    """Upsert every row in df. Returns the list of job IDs seen in this run."""
    seen_ids: list[int] = []

    for row in df.itertuples(index=False):
        job_id = int(row.job_id)
        seen_ids.append(job_id)

        values = {
            "id": job_id,
            "title": getattr(row, "title", None),
            "company_name": getattr(row, "company_name", None),
            "location": getattr(row, "location", None),
            "description": getattr(row, "description", None),
            "experience_level": getattr(row, "experience_level", None),
            "work_type": getattr(row, "work_type", None),
            "job_classification": getattr(row, "job_classification", None),
            "apply_url": row.apply_url,
            "applications_count": str(getattr(row, "applications_count", "") or ""),
            "status": "open",
        }

        stmt = pg_insert(Job).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Job.id],
            set_={
                "applications_count": stmt.excluded.applications_count,
                "status": "open",
            },
        )
        await session.execute(stmt)

    return seen_ids


async def _close_missing_jobs(session: AsyncSession, seen_ids: list[int]) -> int:
    """Mark 'open' jobs absent from this CSV run as 'closed'."""
    stmt = (
        update(Job)
        .where(Job.status == "open")
        .where(Job.id.notin_(seen_ids) if seen_ids else true())
        .values(status="closed")
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def ingest_csv(csv_path: str | Path) -> dict:
    """Ingest a jobs.csv file: upsert present rows, close missing 'open' jobs."""
    csv_path = Path(csv_path)
    df = _load_and_normalize_csv(csv_path)

    async with get_session() as session:
        seen_ids = await _upsert_jobs(session, df)
        closed_count = await _close_missing_jobs(session, seen_ids)
        await session.commit()

    summary = {
        "upserted": len(seen_ids),
        "closed_missing": closed_count,
    }
    logger.info("CSV ingestion complete: %s", summary)
    return summary


async def get_open_job_ids() -> list[int]:
    async with get_session() as session:
        result = await session.execute(select(Job.id).where(Job.status == "open"))
        return [row[0] for row in result.all()]
