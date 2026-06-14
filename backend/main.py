import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before any module that reads env vars is imported.
# Using an absolute path guarantees the correct file regardless of CWD.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

# When uvicorn is launched from the backend/ directory, the project root
# (one level up) is not automatically on sys.path.  Add it so that the
# top-level `models/` package (e.g. models.agent) is importable alongside
# the `api/`, `services/`, and `config` packages that live inside backend/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import agents, analytics, applications, ariel, auth, chat, crm, emails, jobs, outreach, profile, resumes, settings
from config import (
    AUTO_DISCOVERY,
    CREDIT_CONSERVATION_MODE,
    DEV_MAX_JOBS_PER_BOARD,
    DEV_MODE,
    DISCOVERY_INTERVAL_SECONDS,
    TARGET_SEARCH_QUERIES,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    force=True,
)

logger = logging.getLogger(__name__)


async def _enrichment_loop() -> None:
    """
    Automatic enrichment worker — runs every 30 seconds regardless of whether
    AUTO_DISCOVERY is enabled.

    Picks up any job with score_is_proxy=True (including jobs that just came
    through /api/jobs/analyze with a junk LLM response) and runs the full s2
    enrichment pass until analysis is substantive or enrichment_failures reaches
    the hard-stop threshold (ENRICHMENT_MAX_FAILURES).

    This is the primary guarantee that 'Generating deep insights…' never becomes
    a permanent dead end — even if the synchronous analyze pipeline failed to
    produce analysis on the first attempt.

    Backoff schedule (per job, governed by enrichment_failures counter):
      failures=0 → eligible immediately
      failures=1 → eligible (30s has passed since the loop last ran)
      failures=2 → eligible (another 30s passes — total ~60s between first and third attempt)
      failures>=3 → retired; UI shows 'Analysis Unavailable' error state
    """
    from backend.services.active_user import get_active_user_id
    from backend.services.feed_service import refresh_user_scores

    _INTERVAL = 30   # seconds between enrichment sweeps

    logger.info("[enrichment-loop] Automatic enrichment worker started — interval=%ds", _INTERVAL)

    while True:
        await asyncio.sleep(_INTERVAL)
        try:
            user_id = get_active_user_id()
            count   = await refresh_user_scores(user_id)
            if count:
                logger.info(
                    "[enrichment-loop] Enriched %d job(s) for user=%s", count, user_id,
                )
        except Exception:
            # logger.exception prints the full stack trace — critical for diagnosing
            # API-key failures, timeouts, and JSON parse errors from the LLM.
            logger.exception("[enrichment-loop] Unhandled error in enrichment sweep")


async def _discovery_loop() -> None:
    from backend.services.discovery import run_discovery_cycle
    from backend.services.active_user import get_active_user_id

    if not AUTO_DISCOVERY:
        logger.warning(
            "[discovery-loop] AUTO_DISCOVERY=False — background discovery is DISABLED. "
            "Set AUTO_DISCOVERY=True in backend/config.py to re-enable. "
            "Manual single-job analysis via POST /api/jobs/analyze remains fully operational."
        )
        # Sleep indefinitely — task stays alive so cancellation on shutdown works.
        while True:
            await asyncio.sleep(3600)

    logger.info(
        "[discovery-loop] Background task started — interval=%ds  credit_conservation=%s",
        DISCOVERY_INTERVAL_SECONDS, CREDIT_CONSERVATION_MODE,
    )
    while True:
        try:
            # Re-read on every cycle so a newly logged-in user is picked up
            # without requiring a server restart.
            active_user = get_active_user_id()
            await run_discovery_cycle(user_id=active_user)
        except Exception as exc:
            logger.error("[discovery-loop] Unhandled error: %s", exc)
        await asyncio.sleep(DISCOVERY_INTERVAL_SECONDS)


def _seed_scraper_registry() -> None:
    """
    Register default company scrapers into the global SCRAPER_MANAGER.

    The user_id baked into each scraper at construction time is used as a
    fallback only.  The discovery loop and run_all() pass the active user_id
    at call time (read from data/active_user.json), which overrides this value
    so new jobs land in the correct user's feed.  We keep user_id="default"
    here so scrapers remain functional before any user logs in.
    """
    from backend.scrapers.scraper_manager import SCRAPER_MANAGER, scraper_from_config
    from backend.scrapers.drushim_scraper      import DrushimScraper
    from backend.scrapers.alljobs_scraper      import AllJobsScraper
    from backend.scrapers.gotfriends_scraper   import GotfriendsScraper
    from backend.scrapers.dialog_scraper       import DialogScraper
    from backend.scrapers.nisha_scraper        import NishaScraper
    from backend.scrapers.google_dork_scraper  import GoogleDorkScraper

    # ── Company-site adapters (Comeet) ────────────────────────────────────────
    # These scrape specific employer career pages — relevancy gate is applied
    # inside ScraperManager._save_new() since Comeet doesn't do keyword search.
    default_companies = [
        {
            "company_name": "Spark Hire",
            "company_url":  "https://www.comeet.co/jobs/spark-hire/30.005/all",
            "adapter":      "comeet",
            "user_id":      "default",
        },
        {
            "company_name": "Wix",
            "company_url":  "https://www.comeet.co/jobs/wix/ED.30A/all",
            "adapter":      "comeet",
            "user_id":      "default",
        },
    ]

    for cfg in default_companies:
        scraper = scraper_from_config(cfg)
        if scraper:
            SCRAPER_MANAGER.register(scraper)

    # ── Israeli board scrapers — targeted multi-keyword search ────────────────
    # Each board scraper runs one search request per entry in TARGET_SEARCH_QUERIES
    # and discards non-matching titles before any detail-page fetch.
    #
    # Dev-mode cap: when DEV_MODE=True (config.py), each scraper is limited to
    # DEV_MAX_JOBS_PER_BOARD detail-page fetches so the full s1→s4 pipeline
    # completes in seconds rather than minutes during local development.
    # Set DEV_MODE=False in config.py before deploying to production.
    _board_kw: dict = {"max_jobs": DEV_MAX_JOBS_PER_BOARD} if DEV_MODE else {}
    if DEV_MODE:
        logger.info(
            "[startup] DEV_MODE active — board scrapers capped at %d jobs each.",
            DEV_MAX_JOBS_PER_BOARD,
        )

    board_scrapers = [
        DrushimScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default", **_board_kw),
        AllJobsScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default", **_board_kw),
        GotfriendsScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default", **_board_kw),
        DialogScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default", **_board_kw),
        NishaScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default", **_board_kw),
        # "Under the radar" — surfaces roles directly from ATS platforms via Google Dorks
        # before aggregators re-index them (lower competition, earlier pipeline entry).
        # GoogleDorkScraper has no max_jobs param — it is not a paginated board scraper.
        GoogleDorkScraper(keywords=TARGET_SEARCH_QUERIES, user_id="default"),
    ]

    for scraper in board_scrapers:
        SCRAPER_MANAGER.register(scraper)

    logger.info(
        "[startup] ScraperManager seeded with %d scraper(s) (%d board scrapers with %d keywords each).",
        SCRAPER_MANAGER.scraper_count,
        len(board_scrapers),
        len(TARGET_SEARCH_QUERIES),
    )


def purge_irrelevant_jobs(min_score: float = 30.0, dry_run: bool = False) -> dict:
    """
    One-time cleanup utility: remove job rows that fall below quality threshold.

    A row is deleted when EITHER condition is true:
      • match_score < min_score  (default 30.0) — low AI fit, not worth showing
      • title does not match TARGET_SEARCH_QUERIES — not a PM-related role

    Parameters
    ----------
    min_score : float
        Rows with match_score strictly below this value are deleted.
    dry_run   : bool
        When True, counts rows that *would* be deleted but makes no changes.

    Returns
    -------
    dict with keys:
        total       — total rows examined
        deleted     — rows actually removed (0 if dry_run=True)
        dry_run_preview — rows that would be removed (only set when dry_run=True)
    """
    from backend.services.db import ENGINE, JobRow
    from backend.scrapers.relevancy import is_title_relevant
    from sqlalchemy.orm import Session

    with Session(ENGINE) as session:
        all_rows = session.query(JobRow).all()
        to_delete = [
            r for r in all_rows
            if (r.match_score or 0.0) < min_score or not is_title_relevant(r.title or "")
        ]

        result: dict = {"total": len(all_rows), "deleted": 0}

        if dry_run:
            result["dry_run_preview"] = len(to_delete)
            logger.info(
                "[purge] DRY RUN — would delete %d/%d rows (min_score=%.1f)",
                len(to_delete), len(all_rows), min_score,
            )
            return result

        for row in to_delete:
            session.delete(row)
        session.commit()

        result["deleted"] = len(to_delete)
        logger.info(
            "[purge] Deleted %d/%d job rows (min_score=%.1f)",
            len(to_delete), len(all_rows), min_score,
        )
        return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.services.db import init_db
    init_db()
    logger.info("Database initialised.")

    try:
        from backend.services.master_profile_service import bootstrap_from_supplemental
        n = bootstrap_from_supplemental()
        if n:
            logger.info("[startup] Bootstrapped %d answer(s) from supplemental store into master profile", n)
    except Exception as exc:
        logger.warning("[startup] master_profile bootstrap failed (non-fatal): %s", exc)

    try:
        _seed_scraper_registry()
    except Exception as exc:
        logger.warning("[startup] Scraper registry seed failed (non-fatal): %s", exc)

    enrich_task    = asyncio.create_task(_enrichment_loop())
    discovery_task = asyncio.create_task(_discovery_loop())
    try:
        yield
    finally:
        for t in (enrich_task, discovery_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        logger.info("[startup] Background tasks stopped.")


app = FastAPI(title="Job Apply API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ariel.router,        prefix="/api/ariel",        tags=["ariel"])
app.include_router(auth.router,         prefix="/api/auth",         tags=["auth"])
app.include_router(chat.router,         prefix="/api/chat",         tags=["chat"])
app.include_router(jobs.router,         prefix="/api/jobs",         tags=["jobs"])
app.include_router(agents.router,       prefix="/api/agents",       tags=["agents"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(resumes.router,      prefix="/api/resumes",      tags=["resumes"])
app.include_router(settings.router,     prefix="/api/settings",     tags=["settings"])
app.include_router(profile.router,      prefix="/api/profile",      tags=["profile"])
app.include_router(outreach.router,     prefix="/api/outreach",     tags=["outreach"])
app.include_router(analytics.router,    prefix="/api/analytics",    tags=["analytics"])
app.include_router(emails.router,       prefix="/api/webhooks",     tags=["webhooks"])
app.include_router(crm.router,          prefix="/api/crm",          tags=["crm"])


@app.get("/health")
async def health():
    return {"status": "ok"}
