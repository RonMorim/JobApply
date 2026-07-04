"""
Outreach API — LinkedIn message generation endpoints.

Routes
------
POST /api/outreach/message
    Generate a LinkedIn message (consultation, escalation, or headhunter).

POST /api/outreach/headhunter
    Shortcut for headhunter-type messages; pre-fills common agency fields.

POST /api/outreach/generate/{job_id}
    Phase 3 — generate + persist a hiring-manager outreach message for one job,
    grounded in the CV tailored to that job.

GET /api/outreach/{job_id}
    Return the persisted outreach message for a job (null if not generated yet).
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.deps import CurrentUser, get_current_user
from backend.services import job_store
from backend.services.outreach_service import generate_outreach, generate_outreach_message

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class OutreachRequest(BaseModel):
    message_type:   Literal["consultation", "escalation", "headhunter"]
    target_name:    str
    target_title:   str
    target_company: str
    context:        Optional[str] = None
    job_id:         Optional[str] = None  # for escalation — fetches JD for context


class OutreachResponse(BaseModel):
    message_type: str
    message:      str
    word_count:   int


class HeadhunterRequest(BaseModel):
    recruiter_name:    str
    recruiter_title:   Optional[str] = "Recruiter"
    agency_name:       str
    context:           Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/message", response_model=OutreachResponse)
async def generate_message(body: OutreachRequest, user: CurrentUser = Depends(get_current_user)) -> OutreachResponse:
    """
    Generate a LinkedIn outreach message.

    - **consultation**: Short warm opener asking for 5-min advice.  No job ask.
    - **escalation**: Follow-up with embedded 3rd-person summary for internal forwarding.
    - **headhunter**: Direct recruiter pitch — domain, seniority, availability.
    """
    try:
        message = generate_outreach_message(
            message_type   = body.message_type,
            target_name    = body.target_name,
            target_title   = body.target_title,
            target_company = body.target_company,
            context        = body.context or "",
            job_id         = body.job_id,
            user_id        = user.user_id,
        )
    except Exception as exc:
        logger.exception("[outreach] Message generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return OutreachResponse(
        message_type = body.message_type,
        message      = message,
        word_count   = len(message.split()),
    )


@router.post("/headhunter", response_model=OutreachResponse)
async def generate_headhunter_message(body: HeadhunterRequest, user: CurrentUser = Depends(get_current_user)) -> OutreachResponse:
    """
    Shortcut: generate a headhunter-optimised outreach message for a named agency recruiter.
    """
    try:
        message = generate_outreach_message(
            message_type   = "headhunter",
            target_name    = body.recruiter_name,
            target_title   = body.recruiter_title or "Recruiter",
            target_company = body.agency_name,
            context        = body.context or "",
            user_id        = user.user_id,
        )
    except Exception as exc:
        logger.exception("[outreach] Headhunter message generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return OutreachResponse(
        message_type = "headhunter",
        message      = message,
        word_count   = len(message.split()),
    )


# ── Phase 3: job-anchored outreach (generate + persist + fetch) ───────────────

class JobOutreachResponse(BaseModel):
    job_id:       str
    outreach_text: Optional[str]   # null when never generated
    word_count:   int


@router.post("/generate/{job_id}", response_model=JobOutreachResponse)
async def generate_job_outreach(
    job_id: str,
    user:   CurrentUser = Depends(get_current_user),
) -> JobOutreachResponse:
    """Generate + persist an outreach message for one of the caller's jobs."""
    try:
        message = generate_outreach(job_id, user.user_id)
    except ValueError as exc:
        # Job not found for this user — 404, never leak cross-tenant existence.
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("[outreach] generate failed for job %s: %s", job_id, exc)
        raise HTTPException(status_code=502, detail=f"Outreach generation failed: {exc}")

    return JobOutreachResponse(
        job_id        = job_id,
        outreach_text = message,
        word_count    = len(message.split()),
    )


@router.get("/{job_id}", response_model=JobOutreachResponse)
async def get_job_outreach(
    job_id: str,
    user:   CurrentUser = Depends(get_current_user),
) -> JobOutreachResponse:
    """Return the persisted outreach message for a job (null if none yet)."""
    text = job_store.get_outreach_text(job_id, user.user_id)
    return JobOutreachResponse(
        job_id        = job_id,
        outreach_text = text,
        word_count    = len(text.split()) if text else 0,
    )
