"""
Persistent job store backed by SQLite via SQLAlchemy.

All functions preserve the exact same signatures and return types as the
previous in-memory store so the rest of the codebase needs no changes.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.services.db import ENGINE, JobRow
from models.job import DetailedAnalysis, JobMatch, ReasonTag

logger = logging.getLogger(__name__)


# ── Cross-board deduplication fingerprint ────────────────────────────────────

def _normalize_for_dedup(s: str) -> str:
    """
    Normalise a string for dedup comparison:
      - Lower-case
      - Strip Hebrew nikud (combining diacritical marks)
      - Remove punctuation
      - Collapse whitespace
    """
    # Decompose Unicode, then strip combining marks (category Mn = Mark, Nonspacing)
    s = unicodedata.normalize("NFD", s.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def canonical_dedup_key(title: str, company: str, location: str) -> str:
    """
    Return a 16-char hex fingerprint for (title, company, location).

    Used to detect cross-board duplicates: the same role posted on both
    Drushim and AllJobs will share the same key even though the URLs differ.
    The key is intentionally short to avoid uniqueness collisions from minor
    phrasing differences — it acts as a soft filter, not a strict equality check.
    """
    canonical = (
        _normalize_for_dedup(title)
        + "|"
        + _normalize_for_dedup(company)
        + "|"
        + _normalize_for_dedup(location)
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]

# Source priority: higher number wins
_SOURCE_PRIORITY = {'company_site': 3, 'linkedin': 2, 'other': 1}


def _source_rank(source_type: Optional[str]) -> int:
    return _SOURCE_PRIORITY.get(source_type or 'other', 1)


def _infer_source_type(stored: Optional[str], url: Optional[str]) -> str:
    """
    Fill in 'linkedin' when the stored type is 'other' but the URL is from LinkedIn.
    Fixes legacy rows imported before source_type was properly set.
    """
    if stored and stored != 'other':
        return stored
    if url and 'linkedin.com' in url:
        return 'linkedin'
    return stored or 'other'


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _to_row(job: JobMatch) -> JobRow:
    return JobRow(
        job_id=job.job_id,
        title=job.title,
        company=job.company,
        location=job.location,
        score=job.score,
        confidence_score=job.confidence_score,
        culture_fit_score=job.culture_fit_score,
        trajectory_alignment=job.trajectory_alignment,
        company_dna_inference=job.company_dna_inference,
        investigation_points=list(job.investigation_points),
        detailed_analysis={
            "strengths":       list(job.detailed_analysis.strengths),
            "critical_gaps":   list(job.detailed_analysis.critical_gaps),
            "strategic_advice":list(job.detailed_analysis.strategic_advice),
        },
        reasons=[{"kind": r.kind, "label": r.label} for r in job.reasons],
        apply_url=job.apply_url,
        is_new=job.is_new,
        posted_at=job.posted_at,
        why_ron=job.why_ron,
        scoring_rationale=job.scoring_rationale,
        category=job.category,
        applied=job.applied,
        applied_at=job.applied_at,
        source=job.source,
        is_open=job.is_open,
        jd_text=job.jd_text,
        jd_structured=job.jd_structured,
        user_id=job.user_id,
        source_type=job.source_type,
        company_website_url=job.company_website_url,
        status=job.status,
        match_score=job.match_score,
        score_is_proxy=job.score_is_proxy,
        created_at=job.created_at or datetime.now(timezone.utc).isoformat(),
        locale=job.locale,
        dedup_key=canonical_dedup_key(job.title, job.company, job.location),
        enrichment_failures=job.enrichment_failures,
    )


def _from_row(row: JobRow) -> JobMatch:
    da = row.detailed_analysis or {}
    return JobMatch(
        job_id=row.job_id,
        title=row.title,
        company=row.company,
        location=row.location,
        score=row.score,
        confidence_score=row.confidence_score,
        culture_fit_score=row.culture_fit_score,
        trajectory_alignment=row.trajectory_alignment or "",
        company_dna_inference=row.company_dna_inference or "",
        investigation_points=list(row.investigation_points or []),
        detailed_analysis=DetailedAnalysis(
            strengths=da.get("strengths", []),
            critical_gaps=da.get("critical_gaps", []),
            strategic_advice=da.get("strategic_advice", []),
        ),
        reasons=[
            ReasonTag(kind=r["kind"], label=r["label"])
            for r in (row.reasons or [])
        ],
        apply_url=row.apply_url,
        is_new=bool(row.is_new),
        posted_at=row.posted_at or "",
        why_ron=row.why_ron,
        scoring_rationale=row.scoring_rationale,
        category=row.category,
        applied=bool(row.applied),
        applied_at=row.applied_at,
        source=row.source or 'automatic',
        is_open=bool(row.is_open) if row.is_open is not None else True,
        jd_text=row.jd_text,
        jd_structured=row.jd_structured,
        user_id=row.user_id or "default",
        source_type=_infer_source_type(row.source_type, row.apply_url),
        company_website_url=row.company_website_url,
        status=row.status or "new",
        match_score=float(row.match_score) if row.match_score is not None else 0.0,
        score_is_proxy=bool(row.score_is_proxy) if row.score_is_proxy is not None else True,
        created_at=row.created_at,
        locale=row.locale,
        has_tailored_cv=bool(row.tailored_cv),
        enrichment_failures=int(row.enrichment_failures) if row.enrichment_failures is not None else 0,
    )


# ── Public API (same signatures as the old in-memory store) ──────────────────

def save(job: JobMatch) -> None:
    """Upsert a JobMatch: insert on first save, update on re-analysis of the same URL."""
    with Session(ENGINE) as session:
        session.merge(_to_row(job))
        session.commit()


def _upgrade_source_fields(row: JobRow, job: JobMatch) -> None:
    """Overwrite source-origin fields on an existing row with higher-priority data."""
    row.source_type         = job.source_type
    row.apply_url           = job.apply_url or row.apply_url
    row.company_website_url = job.company_website_url or row.company_website_url
    if job.jd_text:
        row.jd_text = job.jd_text
    if job.user_id:
        row.user_id = job.user_id


def save_with_source_priority(job: JobMatch) -> bool:
    """
    Upsert with source priority: company_site > linkedin > other.

    1. Exact apply_url match — upgrade source fields if incoming has higher priority.
    2. dedup_key match — same job cross-posted on multiple boards; keep higher-priority
       source, merge locale/jd_text if the existing row lacks them.
    3. (title, company) match with a lower-priority source — migrate to new source
       (handles LinkedIn → company_site upgrades).
    4. No match — fresh insert.

    Returns True only when a brand-new row was inserted.
    """
    incoming_rank = _source_rank(job.source_type)
    job_dedup_key = canonical_dedup_key(job.title, job.company, job.location)

    with Session(ENGINE) as session:
        # ── 1. Exact URL match ────────────────────────────────────────────────
        if job.apply_url:
            existing = (
                session.query(JobRow)
                .filter(JobRow.apply_url == job.apply_url)
                .first()
            )
            if existing:
                if incoming_rank > _source_rank(existing.source_type):
                    _upgrade_source_fields(existing, job)
                    session.commit()
                    logger.debug(
                        "[job_store] Source upgraded %s → %s for job_id=%s",
                        existing.source_type, job.source_type, existing.job_id,
                    )
                # Always backfill locale if missing
                if not existing.locale and job.locale:
                    existing.locale = job.locale
                    session.commit()
                return False  # already existed

        # ── 2. Cross-board dedup_key match ────────────────────────────────────
        # Catches the same job posted on Drushim, AllJobs, LinkedIn etc.
        # The higher-priority source wins; the lower-priority record is skipped.
        dup_key_row = (
            session.query(JobRow)
            .filter(JobRow.dedup_key == job_dedup_key)
            .first()
        )
        if dup_key_row:
            existing_rank = _source_rank(dup_key_row.source_type)
            if incoming_rank > existing_rank:
                _upgrade_source_fields(dup_key_row, job)
                session.commit()
                logger.info(
                    "[job_store] dedup_key hit: upgraded '%s @ %s' source %s→%s",
                    job.title, job.company, dup_key_row.source_type, job.source_type,
                )
            else:
                # Backfill locale/jd_text if the existing row lacks them
                changed = False
                if not dup_key_row.locale and job.locale:
                    dup_key_row.locale = job.locale
                    changed = True
                if not dup_key_row.jd_text and job.jd_text:
                    dup_key_row.jd_text = job.jd_text
                    changed = True
                if changed:
                    session.commit()
                logger.debug(
                    "[job_store] dedup_key hit (cross-board dup): skipping '%s @ %s' from %s",
                    job.title, job.company, job.source_type,
                )
            return False

        # ── 3. Title + company cross-source dedup (company_site only) ─────────
        if incoming_rank >= _SOURCE_PRIORITY['company_site']:
            dup = (
                session.query(JobRow)
                .filter(
                    func.lower(JobRow.title)   == job.title.strip().lower(),
                    func.lower(JobRow.company) == job.company.strip().lower(),
                    JobRow.source_type         != 'company_site',
                )
                .first()
            )
            if dup:
                logger.info(
                    "[job_store] Upgrading '%s @ %s' source '%s' → 'company_site'",
                    job.title, job.company, dup.source_type,
                )
                _upgrade_source_fields(dup, job)
                session.commit()
                return False

        # ── 4. Fresh insert ───────────────────────────────────────────────────
        session.merge(_to_row(job))
        session.commit()
        return True


def update_scores(
    job_id: str,
    *,
    fit_score: Optional[float] = None,
    ats_score: Optional[float] = None,
) -> bool:
    """Update fit score and/or ATS match_score for a job. Returns True if found."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if not row:
            return False
        if fit_score is not None:
            row.score = max(0.0, float(fit_score))
        if ats_score is not None:
            row.match_score = max(0.0, float(ats_score))
        session.commit()
        return True


def get_all() -> list[JobMatch]:
    """Return all stored jobs sorted by score descending."""
    with Session(ENGINE) as session:
        rows = session.query(JobRow).order_by(JobRow.score.desc()).all()
        return [_from_row(r) for r in rows]


def is_empty() -> bool:
    with Session(ENGINE) as session:
        return session.query(JobRow).count() == 0


def contains_url(url: str) -> bool:
    """Return True if a job with this apply_url is already in the database."""
    with Session(ENGINE) as session:
        return (
            session.query(JobRow)
            .filter(JobRow.apply_url == url)
            .count() > 0
        )


def get_by_id(job_id: str) -> Optional[JobMatch]:
    """Return the stored JobMatch for a job_id, or None if not found."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        return _from_row(row) if row else None


def get_by_url(url: str) -> Optional[JobMatch]:
    """Return the stored JobMatch for a URL, or None if not found."""
    with Session(ENGINE) as session:
        row = (
            session.query(JobRow)
            .filter(JobRow.apply_url == url)
            .first()
        )
        return _from_row(row) if row else None


def mark_closed(job_id: str) -> None:
    """Set is_open=False on an existing job row."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.is_open = False
            session.commit()


def get_categories() -> list[str]:
    """Return sorted list of unique non-null category tags in the database."""
    with Session(ENGINE) as session:
        rows = (
            session.query(JobRow.category)
            .filter(JobRow.category.isnot(None))
            .distinct()
            .all()
        )
        return sorted(r[0] for r in rows)


def get_eligible_for_apply(threshold: float = 85.0) -> list[JobMatch]:
    """Return jobs with score >= threshold that have not been applied to yet."""
    with Session(ENGINE) as session:
        rows = (
            session.query(JobRow)
            .filter(JobRow.score >= threshold, JobRow.applied == False)  # noqa: E712
            .order_by(JobRow.score.desc())
            .all()
        )
        return [_from_row(r) for r in rows]


def mark_applied(job_id: str, applied_at: str) -> None:
    """Set applied=True and record the timestamp on an existing job row."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.applied    = True
            row.applied_at = applied_at
            session.commit()


def get_tailored_cv(job_id: str) -> Optional[dict]:
    """Return the cached tailored CV payload for a job, or None if not yet generated."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        return (row.tailored_cv or None) if row else None


def save_tailored_cv(job_id: str, cv_data: dict, match_score: Optional[dict]) -> None:
    """Persist the generated CV data + match score for a job."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.tailored_cv = {"cv_data": cv_data, "match_score": match_score}
            session.commit()


def get_feed(user_id: str, status_filter: Optional[str] = None) -> List[JobMatch]:
    """
    Return the job feed for a user, sorted by match_score DESC then created_at DESC.

    status_filter: optional JobStatus value ('new', 'saved', 'ignored', 'applied').
    When omitted, all statuses except 'ignored' are returned.
    """
    with Session(ENGINE) as session:
        query = session.query(JobRow).filter(JobRow.user_id == user_id)
        if status_filter:
            query = query.filter(JobRow.status == status_filter)
        else:
            query = query.filter(JobRow.status != "ignored")
        rows = (
            query
            .order_by(JobRow.match_score.desc(), JobRow.created_at.desc())
            .all()
        )
        jobs = [_from_row(r) for r in rows]
        for job in jobs:
            job.is_direct_application = job.source_type == "company_site"
        return jobs


def update_match_score(job_id: str, score: float, is_proxy: bool = False) -> None:
    """Persist a newly computed ATS match_score onto an existing job row.

    Pass is_proxy=False (the default) when this is a full LLM-backed Phase B
    score so the UI can stop showing "Analysing…".  Pass is_proxy=True only
    when persisting the fast Phase A proxy from the scraper.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.match_score   = score
            row.score_is_proxy = is_proxy
            session.commit()


def update_reasons(job_id: str, reasons: list[dict]) -> None:
    """
    Replace the reasons column on an existing job row.
    Each reason must be {kind: 'skill'|'exp'|'loc'|'neg', label: str}.
    Called after proficiency-aware rescoring to surface context tags like
    "Academic Python vs. Professional req." in the UI.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.reasons = reasons
            session.commit()


def update_status(job_id: str, status: str) -> bool:
    """
    Set the status field on an existing job row.
    Returns True if the row was found and updated, False if job_id unknown.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if not row:
            return False
        row.status = status
        session.commit()
        return True


def get_jobs_missing_jd_text(user_id: str, min_score: float = 50.0) -> List[JobMatch]:
    """
    Return jobs for a user with score >= min_score whose jd_text is missing or
    too short to be a real JD (< 100 chars after stripping whitespace).

    Used by the JD backfill task to find jobs worth fetching descriptions for.
    Ordered by score DESC so the highest-value jobs are fetched first.
    """
    with Session(ENGINE) as session:
        rows = (
            session.query(JobRow)
            .filter(
                and_(
                    JobRow.user_id == user_id,
                    JobRow.score   >= min_score,
                    JobRow.apply_url.isnot(None),
                )
            )
            .order_by(JobRow.score.desc())
            .all()
        )
        # Post-filter in Python: jd_text missing or shorter than a real JD
        result = []
        for row in rows:
            text = (row.jd_text or "").strip()
            if len(text) < 100:
                result.append(_from_row(row))
        return result


def update_jd_text(job_id: str, text: str) -> None:
    """Persist fetched JD text onto an existing job row."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.jd_text = text
            session.commit()


def update_jd_structured(job_id: str, structured_json: str) -> None:
    """Persist LLM-structured JD JSON string onto an existing job row."""
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.jd_structured = structured_json
            session.commit()


def update_company(job_id: str, company: str) -> None:
    """Overwrite the company field on an existing job row."""
    if not company or not company.strip():
        return
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.company = company.strip()
            session.commit()


def get_unscored_new_jobs(user_id: str) -> List[JobMatch]:
    """
    Return jobs for a user that are status='new' and have not yet been
    ATS-scored (match_score == 0.0).  Used by refresh_user_scores().
    """
    with Session(ENGINE) as session:
        rows = (
            session.query(JobRow)
            .filter(
                and_(
                    JobRow.user_id == user_id,
                    JobRow.status  == "new",
                    JobRow.match_score == 0.0,
                )
            )
            .all()
        )
        return [_from_row(r) for r in rows]


def get_jobs_needing_llm_enrichment(user_id: str) -> List[JobMatch]:
    """
    Return all jobs for user_id that need the s2 LLM enrichment pass.

    A job needs enrichment when EITHER:
      • match_score == 0.0  — never scored at all (legacy / pre-two-phase rows)
      • why_ron IS NULL     — locally scored in s1 but LLM brief not yet written

    Jobs are ordered by match_score DESC so the most promising ones are
    enriched first when the batch is rate-limited by the Semaphore.
    """
    with Session(ENGINE) as session:
        rows = (
            session.query(JobRow)
            .filter(
                and_(
                    JobRow.user_id == user_id,
                    JobRow.status.in_(["new", "saved"]),
                    or_(
                        JobRow.match_score == 0.0,
                        JobRow.why_ron.is_(None),
                    ),
                )
            )
            .order_by(JobRow.match_score.desc())
            .all()
        )
        return [_from_row(r) for r in rows]


def update_why_ron(job_id: str, why_ron: str) -> None:
    """
    Persist the LLM-generated 'why apply' brief onto an existing job row.

    Called by feed_service after s2 enrichment completes.  A non-NULL
    why_ron signals that this job has been fully LLM-scored and should
    not be re-processed in subsequent s2 runs.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            row.why_ron = why_ron
            session.commit()


def increment_enrichment_failures(job_id: str) -> int:
    """
    Increment the enrichment_failures counter for a job and return the new count.
    Called when the s2 LLM pass returns a non-substantive result.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            current = int(row.enrichment_failures or 0)
            row.enrichment_failures = current + 1
            session.commit()
            return row.enrichment_failures
    return 0


def reset_job_for_enrichment(job_id: str) -> bool:
    """
    Force a job row back to "un-enriched" state so the next s2 run picks it
    up unconditionally, even if why_ron was previously set by a DEV mock or
    an earlier enrichment pass.

    Sets:
      • match_score = 0.0  — makes the job visible to get_jobs_needing_llm_enrichment
      • why_ron     = None — clears the "already enriched" sentinel

    Only touches the row if it exists.  Returns True when found, False otherwise.
    Intended for DEV_MODE pre-enrichment resets; safe to call in production but
    generally not needed there.
    """
    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if not row:
            return False
        row.match_score = 0.0
        row.why_ron     = None
        session.commit()
        return True


# ── Legacy helper (used by the LangGraph orchestrator workflow) ───────────────

def build_from_result(result: dict) -> JobMatch:
    """Convert a run_analysis() result dict into a JobMatch for storage."""
    job_info = result.get("job_info", {})
    gap      = result.get("gap_analysis", {})
    truth    = result.get("truth_report", {})

    score  = truth.get("fit_score") or gap.get("overall_fit_score", 50)
    url    = job_info.get("url", "")
    job_id = f"analyzed-{abs(hash(url)) % 10_000_000}"

    reasons: list[ReasonTag] = []
    for match in gap.get("direct_matches", [])[:3]:
        req      = match.get("requirement", "")
        evidence = match.get("evidence", "")
        label    = req[:40] if req else evidence[:40]
        kind     = "exp" if any(w in req.lower() for w in ["year", "experience", "background"]) else "skill"
        if label:
            reasons.append(ReasonTag(kind=kind, label=label))

    location = job_info.get("location", "")
    if "remote" in location.lower():
        reasons.append(ReasonTag(kind="loc", label="Remote"))

    for gap_item in gap.get("profile_gaps", []):
        if gap_item.get("severity") == "high":
            label = gap_item.get("gap", "")[:40]
            if label:
                reasons.append(ReasonTag(kind="neg", label=label))
            break

    now       = datetime.now(timezone.utc)
    posted_at = now.strftime("%-I:%M %p").lower() + " today"

    return JobMatch(
        job_id=job_id,
        title=job_info.get("title", "Analyzed Role"),
        company=job_info.get("company", "Unknown Company"),
        location=location or "Unknown",
        score=float(score),
        confidence_score=50,
        culture_fit_score=50,
        trajectory_alignment="",
        company_dna_inference="",
        detailed_analysis=DetailedAnalysis(
            strengths=[],
            critical_gaps=[],
            strategic_advice=[],
        ),
        investigation_points=[],
        reasons=reasons,
        apply_url=url or None,
        is_new=True,
        posted_at=posted_at,
        why_ron=result.get("why_ron") or None,
    )
