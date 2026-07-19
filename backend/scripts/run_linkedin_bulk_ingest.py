"""
run_linkedin_bulk_ingest.py

CLI driver for the LinkedIn Bulk Import pipeline (JOB-76/JOB-81, Converge).
Ingests a daily jobs.csv export into the main SQLite job_store — replaces
the deleted backend/ingestion/run_pipeline.py, which targeted a standalone
Postgres database instead.

Usage
-----
    venv/bin/python -m backend.scripts.run_linkedin_bulk_ingest path/to/jobs.csv --user-id <uid>
    venv/bin/python -m backend.scripts.run_linkedin_bulk_ingest path/to/jobs.csv --user-id <uid> --skip-validation
    venv/bin/python -m backend.scripts.run_linkedin_bulk_ingest path/to/jobs.csv --user-id <uid> --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.scrapers.linkedin_bulk_scraper import LinkedInBulkCsvScraper
from backend.scrapers.linkedin_bulk_validator import DEFAULT_CONCURRENCY, validate_open_linkedin_bulk_jobs
from backend.scrapers.scraper_manager import ScraperManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run(csv_path: str, user_id: str, skip_validation: bool, concurrency: int) -> None:
    scraper = LinkedInBulkCsvScraper(csv_path, user_id=user_id)
    jobs = await scraper.fetch_jobs()

    # Reuses the exact same tenant-salting, relevancy gate, and
    # save_with_source_priority dedup every other scraper goes through —
    # not a parallel persistence path.
    saved = ScraperManager._save_new(jobs, user_id=user_id)
    logger.info("Ingestion complete: %d fetched, %d new — user_id=%s", len(jobs), saved, user_id)

    if not skip_validation:
        validation_summary = await validate_open_linkedin_bulk_jobs(user_id, concurrency=concurrency)
        logger.info("Validation summary: %s", validation_summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Bulk Import pipeline (Converge)")
    parser.add_argument("csv_path", help="Path to the daily jobs.csv file")
    parser.add_argument("--user-id", required=True, help="Owner of the ingested jobs")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Only run CSV ingestion, skip the closure re-validation pass",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Max concurrent validation requests",
    )
    args = parser.parse_args()

    asyncio.run(run(args.csv_path, args.user_id, args.skip_validation, args.concurrency))


if __name__ == "__main__":
    main()
