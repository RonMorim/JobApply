"""Async validation agent: re-checks 'open' jobs against LinkedIn guest-mode pages.

For every job currently marked 'open':
  - Fetch the clean LinkedIn job URL anonymously (no auth/session cookies).
  - If the page contains "No longer accepting applications", mark it 'closed'
    and skip further parsing (nothing else worth extracting from a dead post).
  - Otherwise, keep it 'open', and refresh `description` /
    `linkedin_posted_at` from the page content.

Concurrency is bounded by a semaphore, and every request is preceded by a
small randomized delay, to stay within a scrape rate LinkedIn is unlikely
to flag as abusive.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timedelta, timezone

import aiohttp
from bs4 import BeautifulSoup
from sqlalchemy import select

from backend.ingestion.csv_ingest import normalize_job_url
from backend.ingestion.db import get_session
from backend.ingestion.models import Job

logger = logging.getLogger(__name__)

CLOSED_MARKER = "No longer accepting applications"

DEFAULT_CONCURRENCY = 5
MIN_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 3.0
REQUEST_TIMEOUT_SECONDS = 15

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _parse_relative_posted_at(text: str) -> datetime | None:
    """Best-effort parse of LinkedIn's relative posting strings ('2 days ago')."""
    if not text:
        return None
    match = re.search(r"(\d+)\s+(day|hour|week|month|minute)s?\s+ago", text, re.I)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    now = datetime.now(timezone.utc)
    unit_map = {
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
        "week": timedelta(weeks=amount),
        "month": timedelta(days=amount * 30),
    }
    delta = unit_map.get(unit)
    return now - delta if delta else None


def _extract_job_details(html: str) -> dict:
    """Parse description text and posted-at timestamp out of a guest job page."""
    soup = BeautifulSoup(html, "html.parser")

    description_el = soup.select_one(
        ".description__text, .show-more-less-html__markup, [class*='description']"
    )
    description = description_el.get_text(separator="\n", strip=True) if description_el else None

    posted_at_el = soup.select_one(
        ".posted-time-ago__text, [class*='posted-time-ago'], time"
    )
    posted_text = posted_at_el.get_text(strip=True) if posted_at_el else ""
    linkedin_posted_at = _parse_relative_posted_at(posted_text)

    return {"description": description, "linkedin_posted_at": linkedin_posted_at}


async def _fetch_job_page(
    session: aiohttp.ClientSession, job_id: int
) -> tuple[int, str | None]:
    url = normalize_job_url(str(job_id))
    try:
        async with session.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        ) as response:
            if response.status != 200:
                logger.warning("Job %s fetch returned HTTP %s", job_id, response.status)
                return job_id, None
            return job_id, await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.warning("Job %s fetch failed: %s", job_id, exc)
        return job_id, None


async def _validate_one_job(
    job_id: int,
    http_session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Fetch + parse one job page. Returns an update payload, or None on fetch failure."""
    async with semaphore:
        await asyncio.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
        job_id, html = await _fetch_job_page(http_session, job_id)

    if html is None:
        return None

    if CLOSED_MARKER in html:
        return {"id": job_id, "status": "closed"}

    details = _extract_job_details(html)
    return {
        "id": job_id,
        "status": "open",
        "description": details["description"],
        "linkedin_posted_at": details["linkedin_posted_at"],
    }


async def _apply_updates(updates: list[dict]) -> None:
    async with get_session() as db_session:
        for update_payload in updates:
            job_id = update_payload.pop("id")
            job = await db_session.get(Job, job_id)
            if job is None:
                continue
            for field, value in update_payload.items():
                if value is not None or field == "status":
                    setattr(job, field, value)
        await db_session.commit()


async def validate_open_jobs(concurrency: int = DEFAULT_CONCURRENCY) -> dict:
    """Re-validate every 'open' job against its live LinkedIn guest page."""
    async with get_session() as db_session:
        result = await db_session.execute(select(Job.id).where(Job.status == "open"))
        job_ids = [row[0] for row in result.all()]

    if not job_ids:
        logger.info("No open jobs to validate")
        return {"checked": 0, "closed": 0, "still_open": 0, "failed": 0}

    semaphore = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as http_session:
        tasks = [_validate_one_job(jid, http_session, semaphore) for jid in job_ids]
        results = await asyncio.gather(*tasks)

    updates = [r for r in results if r is not None]
    failed = len(results) - len(updates)
    closed = sum(1 for u in updates if u["status"] == "closed")
    still_open = len(updates) - closed

    await _apply_updates(updates)

    summary = {
        "checked": len(job_ids),
        "closed": closed,
        "still_open": still_open,
        "failed": failed,
    }
    logger.info("Validation pass complete: %s", summary)
    return summary
