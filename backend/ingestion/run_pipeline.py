"""CLI entrypoint: ingest jobs.csv, then run the validation agent.

Usage:
    python -m backend.ingestion.run_pipeline path/to/jobs.csv
    python -m backend.ingestion.run_pipeline path/to/jobs.csv --skip-validation
    python -m backend.ingestion.run_pipeline path/to/jobs.csv --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from backend.ingestion.csv_ingest import ingest_csv
from backend.ingestion.db import dispose_engine, init_db
from backend.ingestion.validator_agent import DEFAULT_CONCURRENCY, validate_open_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run(csv_path: str, skip_validation: bool, concurrency: int) -> None:
    await init_db()
    try:
        ingest_summary = await ingest_csv(csv_path)
        logger.info("Ingestion summary: %s", ingest_summary)

        if not skip_validation:
            validation_summary = await validate_open_jobs(concurrency=concurrency)
            logger.info("Validation summary: %s", validation_summary)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn job ingestion pipeline")
    parser.add_argument("csv_path", help="Path to the daily jobs.csv file")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Only run CSV ingestion, skip the LinkedIn validation agent",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Max concurrent validation requests",
    )
    args = parser.parse_args()

    asyncio.run(run(args.csv_path, args.skip_validation, args.concurrency))


if __name__ == "__main__":
    main()
