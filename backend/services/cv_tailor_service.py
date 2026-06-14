"""
CvTailorService — generates a focused, job-specific CV brief for the feed card.

Distinct from TailorAgent (which produces a full PDF-ready CV data dict),
this service produces a lightweight "tailor brief":

  • positioning_summary — 2-3 sentence pitch for this specific role
  • tailored_sections — top 2-3 experience roles with rewritten bullets

Philosophy
----------
The LLM receives THREE grounding sources and is instructed to work ONLY
from them — never to invent experience, metrics, or claims:
  1. build_full_text() — full profile narrative
  2. get_skill_proficiencies() — verified proficiency levels from Q&A sessions
  3. job.jd_text — the raw JD (or a thin proxy if not yet scraped)

Caching
-------
Results are persisted in the existing `tailored_cv` JSON column under the
"tailor_brief" key so subsequent opens are instant:
  {"cv_data": {...}, "match_score": {...}, "tailor_brief": {...}}
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from backend.services import job_store
from backend.services.user_profile import USER_PROFILE, build_full_text
from backend.services.master_profile_service import get_skill_proficiencies
from models.job import JobMatch

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

logger = logging.getLogger(__name__)

_MODEL      = "claude-sonnet-4-6"   # quality-sensitive — rewriting real bullets
_MAX_TOKENS = 3000
_MIN_JD_LEN = 60   # chars — below this we warn but still proceed

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a senior tech recruiter and ATS optimization expert with 20 years of experience \
placing candidates at top B2B SaaS companies in EMEA.

Your task is to analyse how a candidate's VERIFIED experience intersects with a job \
description, then produce a structured JSON brief that:
  1. Positions the candidate for this specific role.
  2. Rewrites 3-5 key experience bullets per relevant role to emphasise genuine overlaps \
     with the JD — using the JD's own terminology where it fits naturally.

ABSOLUTE RULES — violating any of these invalidates the output:
  • NEVER invent experience, metrics, company names, dates, or skills not present \
    in the CANDIDATE_PROFILE or PROFICIENCY_MAP.
  • ONLY reframe authentic experience using the JD's language — do not add \
    fictional quantification (e.g. "increased revenue by 40%") unless the number \
    already appears in the profile.
  • Output ONLY the raw JSON object — no markdown fences, no preamble, no explanation.
  • All bullet strings must be under 220 characters.
  • Include only the 2-3 most relevant experience roles in tailored_sections; \
    omit roles with negligible signal for this JD.
  • You MUST output a maximum of 4 bullets for the most recent role and 2 bullets \
    for all older roles. Brevity is critical — the output must fit a single A4 page.
"""

_USER_TMPL = """\
CANDIDATE_PROFILE:
{profile}

PROFICIENCY_MAP (skill → verified level: professional | academic | none | unknown):
{proficiency_block}

JOB_TITLE: {title}
COMPANY: {company}
LOCATION: {location}

JOB_DESCRIPTION:
{jd_text}

─────────────────────────────────────────────────────────────────────────────
Produce a single JSON object matching this exact schema (no extra keys):

{{
  "positioning_summary": "2-3 sentences specifically positioning this candidate for THIS role at THIS company. Reference the company and role explicitly. Be concrete — not generic.",

  "tailored_sections": [
    {{
      "role": "Job title held",
      "company": "Employer name",
      "dates": "Date range",
      "bullets": [
        "Bullet rewritten to highlight JD overlap — max 220 chars. No invented facts.",
        "..."
      ]
    }}
  ]
}}

For tailored_sections, only include the 2-3 roles with the strongest signal for this JD.
BULLET LIMITS (hard): most recent role → max 4 bullets; every other role → max 2 bullets.
"""


# ── Proficiency block builder ─────────────────────────────────────────────────

def _build_proficiency_block() -> str:
    """Format the skill→level map into a readable block for the prompt."""
    proficiencies = get_skill_proficiencies()
    if not proficiencies:
        return "(No verified proficiency data — profile Q&A not yet completed)"

    lines = []
    for skill, level in sorted(proficiencies.items()):
        lines.append(f"  • {skill}: {level}")
    return "\n".join(lines)


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """
    Extract the first valid JSON object from the model response.
    Handles cases where the model accidentally wraps output in markdown fences.
    """
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", raw).strip()

    # Try the whole string first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back: find the outermost {...}
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from model response. "
                     f"Raw (first 400 chars): {raw[:400]}")


# ── Result validation / normalisation ────────────────────────────────────────

def _normalise(raw_dict: dict, job: JobMatch) -> dict:
    """
    Ensure all required keys exist and value types are correct.
    Fills in safe defaults rather than raising, so partial outputs are usable.
    """
    brief: dict = {
        "job_id":              job.job_id,
        "job_title":           job.title,
        "company":             job.company,
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "positioning_summary": str(raw_dict.get("positioning_summary", "")),
        "tailored_sections":   [],
    }

    for section in raw_dict.get("tailored_sections", []):
        if not isinstance(section, dict):
            continue
        brief["tailored_sections"].append({
            "role":    str(section.get("role", "")),
            "company": str(section.get("company", "")),
            "dates":   str(section.get("dates", "")),
            "bullets": [str(b) for b in section.get("bullets", []) if b],
        })

    return brief


# ── Cache helpers ─────────────────────────────────────────────────────────────

def get_cached_tailor_brief(job_id: str) -> Optional[dict]:
    """Return the cached tailor brief for a job, or None if not yet generated."""
    cached = job_store.get_tailored_cv(job_id)
    if cached and isinstance(cached, dict):
        return cached.get("tailor_brief")
    return None


def _save_tailor_brief(job_id: str, brief: dict) -> None:
    """Persist the brief under the tailor_brief key in the tailored_cv JSON column."""
    from backend.services.db import ENGINE, JobRow
    from sqlalchemy.orm import Session

    with Session(ENGINE) as session:
        row = session.get(JobRow, job_id)
        if row:
            existing = dict(row.tailored_cv or {})
            existing["tailor_brief"] = brief
            row.tailored_cv = existing
            session.commit()


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_tailor_brief(job_id: str, force_refresh: bool = False) -> dict:
    """
    Generate (or return cached) a tailor brief for the given job.

    Parameters
    ----------
    job_id        : DB identifier of the job
    force_refresh : when True, bypass the cache and re-generate

    Returns
    -------
    dict matching the tailor brief schema (see _normalise()).

    Raises
    ------
    ValueError  when the job doesn't exist or has no usable JD/profile text.
    RuntimeError on LLM API failure.
    """
    # ── 1. Load job ───────────────────────────────────────────────────────────
    job = job_store.get_by_id(job_id)
    if not job:
        raise ValueError(f"Job {job_id!r} not found in the store.")

    # ── 2. Check cache ────────────────────────────────────────────────────────
    if not force_refresh:
        cached = get_cached_tailor_brief(job_id)
        if cached:
            logger.info("[cv_tailor] Cache hit for job_id=%s", job_id)
            return cached

    # ── 3. Prepare context ────────────────────────────────────────────────────
    profile_text     = build_full_text()
    proficiency_block = _build_proficiency_block()

    jd_text = (job.jd_text or "").strip()
    if len(jd_text) < _MIN_JD_LEN:
        # Thin proxy — JD not yet scraped. Use what we have.
        jd_text = (
            f"Job title: {job.title}\n"
            f"Company:   {job.company}\n"
            f"Location:  {job.location}\n\n"
            f"(Full job description not yet available — fetch it via 'Fetch Details' "
            f"for a more precise tailoring.)"
        )
        logger.warning(
            "[cv_tailor] JD text too short for job %s (%s @ %s) — using thin proxy",
            job_id, job.title, job.company,
        )

    # ── 4. Build and call the LLM ─────────────────────────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    user_msg = _USER_TMPL.format(
        profile           = profile_text,
        proficiency_block = proficiency_block,
        title             = job.title,
        company           = job.company,
        location          = job.location or "Israel",
        jd_text           = jd_text[:4000],   # cap to avoid token overflow
    )

    logger.info(
        "[cv_tailor] Generating brief for '%s @ %s' (job_id=%s, jd_len=%d)",
        job.title, job.company, job_id, len(jd_text),
    )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        response = await client.messages.create(
            model      = _MODEL,
            max_tokens = _MAX_TOKENS,
            system     = _SYSTEM,
            messages   = [{"role": "user", "content": user_msg}],
        )
    except anthropic.APIError as exc:
        raise RuntimeError(f"Claude API error: {exc}") from exc

    raw_text = response.content[0].text if response.content else ""

    # ── 5. Parse and normalise ────────────────────────────────────────────────
    try:
        raw_dict = _extract_json(raw_text)
    except ValueError as exc:
        logger.error("[cv_tailor] JSON extraction failed: %s", exc)
        raise RuntimeError(f"Model returned unparseable output: {exc}") from exc

    brief = _normalise(raw_dict, job)

    # ── 6. Cache and return ───────────────────────────────────────────────────
    try:
        _save_tailor_brief(job_id, brief)
    except Exception as exc:
        logger.warning("[cv_tailor] Failed to cache brief for job %s: %s", job_id, exc)

    logger.info(
        "[cv_tailor] Brief generated for '%s @ %s' — %d sections",
        job.title, job.company,
        len(brief["tailored_sections"]),
    )
    return brief
