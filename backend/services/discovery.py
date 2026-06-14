"""
DiscoveryPipeline — automated job discovery using LinkedIn scraper + MatcherAgent.

Interval and credit behaviour are controlled by backend/config.py:
  DISCOVERY_INTERVAL_SECONDS  — how often this cycle runs (set in main.py loop)
  CREDIT_CONSERVATION_MODE    — when True, fetch_descriptions is forced to False
                                 so no JD text is scraped during auto-discovery.
                                 Full descriptions are only fetched on explicit
                                 user action ("Fetch Missing Details" / card open).
  TARGET_SEARCH_QUERIES       — job-title search terms; discovery only submits
                                 these targeted searches, not a broad generic feed.
  MAX_RELEVANT_JOBS           — hard cap on new jobs saved per cycle; pagination
                                 halts immediately once this limit is reached.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from backend.agents.matcher import MatcherAgent
from backend.config import (
    CREDIT_CONSERVATION_MODE,
    TARGET_SEARCH_QUERIES,
    MAX_RELEVANT_JOBS,
)
from backend.integrations.job_scraper import get_latest_jobs
from backend.scrapers.relevancy import is_title_relevant
from backend.services import job_store
import backend.services.agent_store as agent_store
from models.job import JobMatch, RawJobPosting

# Minimum JD characters required before we attempt structuring + scoring.
# Below this the text is just the title+company header line — not a real JD.
_MIN_JD_FOR_ENRICHMENT = 300

logger = logging.getLogger(__name__)


async def _enrich_job(match: JobMatch, user_id: str) -> None:
    """
    Run JD structuring + LLM composite scoring for a freshly saved discovery job.

    Called immediately after job_store.save() inside run_discovery_cycle().
    On success, flips status 'analysing' → 'new' so the job surfaces in the feed.

    When CREDIT_CONSERVATION_MODE is True the description is empty (just the
    title/company/location header), so there is no usable JD text to structure
    or score.  In that case we log the deferral and return; the job stays
    'analysing' until the user triggers a JD backfill.
    """
    jd_text = (match.jd_text or "").strip()

    if len(jd_text) < _MIN_JD_FOR_ENRICHMENT:
        logger.info(
            "[discovery] enrich DEFERRED — job_id=%s JD too thin (%d chars); "
            "will be enriched after JD backfill (CREDIT_CONSERVATION_MODE=%s)",
            match.job_id, len(jd_text), CREDIT_CONSERVATION_MODE,
        )
        return

    structured_ok = False
    scored_ok     = False

    # ── JD structuring ─────────────────────────────────────────────────────────
    try:
        from backend.services.jd_structure_service import structure_jd, extract_company_from_structured
        structured = await asyncio.to_thread(structure_jd, jd_text)
        if structured:
            job_store.update_jd_structured(match.job_id, structured)
            structured_ok = True
            logger.info("[discovery] enrich: JD structured — job_id=%s", match.job_id)
            extracted_company = extract_company_from_structured(structured)
            if extracted_company:
                job_store.update_company(match.job_id, extracted_company)
                logger.info(
                    "[discovery] enrich: company overwritten → '%s' (was '%s') — job_id=%s",
                    extracted_company, match.company, match.job_id,
                )
        else:
            logger.warning(
                "[discovery] enrich: JD structuring returned None — job_id=%s", match.job_id
            )
    except Exception as exc:
        logger.exception(
            "[discovery] ENRICHMENT_FAILURE step=jd_structure job_id=%s "
            "error_type=%s error=%s",
            match.job_id, type(exc).__name__, exc,
        )

    # ── LLM composite scoring ──────────────────────────────────────────────────
    try:
        from backend.services.feed_service import (
            _build_profile_cv_proxy,
            is_substantive_analysis,
        )
        from backend.services.match_score_service import compute_match_score_async
        from backend.services.user_profile import USER_PROFILE

        cv_proxy = _build_profile_cv_proxy(USER_PROFILE)
        result   = await compute_match_score_async(
            cv_data            = cv_proxy,
            jd_text            = jd_text,
            run_llm_validation = True,
            job_title          = match.title,
            company_name       = match.company or "",
        )

        analysis_ok = is_substantive_analysis(result.why_ron)
        # Only mark as fully scored when analysis is real.  A junk why_ron
        # keeps is_proxy=True so the enrichment loop re-attempts it.
        job_store.update_match_score(
            match.job_id, float(result.total), is_proxy=not analysis_ok
        )

        if analysis_ok:
            job_store.update_why_ron(match.job_id, result.why_ron)
            scored_ok = True
        else:
            job_store.increment_enrichment_failures(match.job_id)
            logger.warning(
                "[discovery] ENRICHMENT_FAILURE step=analysis job_id=%s "
                "LLM returned non-substantive why_ron=%r — "
                "keeping score_is_proxy=True for enrichment loop retry",
                match.job_id, (result.why_ron or "")[:80],
            )

        # Populate reason tags so the feed card header shows gap badges.
        if result.proficiency_notes:
            try:
                from backend.services.feed_service import _proficiency_reason_tags
                tags = _proficiency_reason_tags(result.proficiency_notes)
                if tags:
                    job_store.update_reasons(match.job_id, tags)
            except Exception as tag_exc:
                logger.debug(
                    "[discovery] enrich: reason tags failed (non-critical) — job_id=%s: %s",
                    match.job_id, tag_exc,
                )

        logger.info(
            "[discovery] enrich: composite=%.1f analysis=%s — job_id=%s",
            result.total, "✓" if analysis_ok else "∅", match.job_id,
        )
    except Exception as exc:
        job_store.increment_enrichment_failures(match.job_id)
        logger.exception(
            "[discovery] ENRICHMENT_FAILURE step=scoring job_id=%s "
            "error_type=%s error=%s",
            match.job_id, type(exc).__name__, exc,
        )

    # ── Finalise: flip 'analysing' → 'new' only when both steps succeeded ──────
    if structured_ok and scored_ok:
        job_store.update_status(match.job_id, "new")
        logger.info(
            "[discovery] enrich COMPLETE — job_id=%s '%s' @ '%s' status='new'",
            match.job_id, match.title, match.company,
        )
    else:
        logger.info(
            "[discovery] enrich INCOMPLETE — job_id=%s stays 'analysing' "
            "(structured=%s scored=%s) — enrichment loop will retry",
            match.job_id, structured_ok, scored_ok,
        )


# Build targeted query list from config.
# All TARGET_SEARCH_QUERIES map to the "Product" category.
# LinkedIn handles both English and Hebrew search terms.
_QUERIES: list[tuple[str, str]] = [(q, "Product") for q in TARGET_SEARCH_QUERIES]
_LOCATION = "Israel"


async def run_discovery_cycle(user_id: str = "default") -> None:
    """
    Run one full discovery cycle: search LinkedIn → filter → analyse → save.

    Parameters
    ----------
    user_id : str
        The owner assigned to every newly saved job.  Pass the authenticated
        user's UUID so jobs immediately appear in their feed.  Falls back to
        'default' for legacy / pre-auth operation.
    """
    logger.info(
        "━━━ Discovery cycle starting — %d targeted queries, cap=%d, user=%r ━━━",
        len(_QUERIES), MAX_RELEVANT_JOBS, user_id,
    )

    # ── Seed agent registry for this user (no-op if already seeded) ──────────
    agent_store.ensure_user_seeded(user_id)

    # ── Scraper agent: active ─────────────────────────────────────────────────
    agent_store.set_active("s1", f"Searching LinkedIn ({len(_QUERIES)} queries) · Israel")

    agent      = MatcherAgent()
    discovered = 0
    skipped    = 0
    saved      = 0

    try:
        for query, category in _QUERIES:
            # ── Global cap check ─────────────────────────────────────────────
            if saved >= MAX_RELEVANT_JOBS:
                logger.info(
                    "[discovery] Hit MAX_RELEVANT_JOBS=%d — halting pagination.",
                    MAX_RELEVANT_JOBS,
                )
                break

            logger.info("[discovery] Searching: '%s' in %s (category=%s)", query, _LOCATION, category)

            try:
                # When CREDIT_CONSERVATION_MODE is active, skip full JD scraping
                # during automatic discovery — descriptions are fetched only on
                # explicit user request (inline card fetch / bulk backfill button).
                jobs = await asyncio.to_thread(
                    get_latest_jobs,
                    job_title=query,
                    location=_LOCATION,
                    fetch_descriptions=not CREDIT_CONSERVATION_MODE,
                )
            except Exception as exc:
                logger.warning("[discovery] Search failed for '%s': %s", query, exc)
                continue

            for job in jobs:
                # ── Per-job cap check ─────────────────────────────────────────
                if saved >= MAX_RELEVANT_JOBS:
                    break

                # Skip simulated fallback entries — they are not real postings
                if job.get("source") == "simulated":
                    skipped += 1
                    continue

                url = job.get("url", "").strip()

                # Deduplication: skip if this URL is already in the store
                if not url or job_store.contains_url(url):
                    logger.debug(
                        "[discovery] SKIP (dup) %s @ %s",
                        job.get("title", "?"), job.get("company", "?"),
                    )
                    skipped += 1
                    continue

                # ── Pre-scrape relevancy gate ─────────────────────────────────
                # Check title from listing metadata BEFORE calling MatcherAgent
                # so we burn zero LLM credits on non-PM postings.
                title = job.get("title", "")
                if not is_title_relevant(title):
                    logger.debug(
                        "[discovery] SKIP (irrelevant) '%s' @ %s",
                        title, job.get("company", "?"),
                    )
                    skipped += 1
                    continue

                discovered += 1

                # ── Sourcing Specialist agent: active ─────────────────────────
                agent_store.set_active(
                    "s2",
                    f"Analysing '{title[:40]}' @ {job.get('company', '?')[:30]}",
                )

                description = job.get("description", "")
                raw_text = "\n\n".join(filter(None, [
                    f"{job.get('title', '')} — {job.get('company', '')} — {job.get('location', '')}",
                    description,
                ]))

                posting = RawJobPosting(
                    id=job.get("job_id") or str(uuid.uuid4()),
                    title=title,
                    company=job.get("company", "Unknown Company"),
                    source_url=url,
                    raw_text=raw_text,
                    scraped_at=datetime.now(timezone.utc).isoformat(),
                )

                try:
                    match = await agent.match(posting)
                except ValueError as exc:
                    logger.warning(
                        "[discovery] SKIP (content guard) %s @ %s — %s",
                        posting.title, posting.company, exc,
                    )
                    skipped += 1
                    discovered -= 1
                    continue
                except Exception as exc:
                    logger.error(
                        "[discovery] ERROR analysing %s @ %s — %s",
                        posting.title, posting.company, exc,
                    )
                    skipped += 1
                    discovered -= 1
                    continue

                # ── Assign job to the authenticated user ──────────────────────
                match.category = category
                match.user_id  = user_id   # override so feed is scoped correctly

                # ── Content Strategist: brief active flash ────────────────────
                agent_store.set_active("s3", f"Writing 'Why apply' brief for '{title[:40]}'")
                # Quality Guard: validates the match output
                agent_store.set_active("s4", f"Verifying claims for '{title[:40]}'")

                job_store.save(match)
                saved += 1
                logger.info(
                    "[discovery] saved 'analysing' [%s] — %s @ %s (%s)",
                    category, match.title, match.company, match.location,
                )

                # ── Inline enrichment: structure JD + composite score ─────────
                # When JD text is available (CREDIT_CONSERVATION_MODE=False) this
                # completes the job immediately (status → 'new').  When the text
                # is too thin (CREDIT_CONSERVATION_MODE=True) the call returns
                # early and the job stays 'analysing' until a JD backfill runs.
                try:
                    await _enrich_job(match, user_id)
                except Exception as enrich_exc:
                    logger.warning(
                        "[discovery] _enrich_job raised unexpectedly for job_id=%s: %s",
                        match.job_id, enrich_exc,
                    )

                # After each job is saved, return supporting agents to idle
                agent_store.set_idle("s3")
                agent_store.set_idle("s4")

    finally:
        # Always return agents to idle — even on unexpected exception
        agent_store.set_idle("s1")
        agent_store.set_idle("s2")
        agent_store.set_idle("s3")
        agent_store.set_idle("s4")

    logger.info(
        "━━━ Discovery cycle done — discovered=%d  skipped=%d  saved=%d  cap=%d  user=%r ━━━",
        discovered, skipped, saved, MAX_RELEVANT_JOBS, user_id,
    )
