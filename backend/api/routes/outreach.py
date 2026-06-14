"""
Outreach API — LinkedIn message generation endpoints.

Routes
------
POST /api/outreach/message
    Generate a LinkedIn message (consultation, escalation, or headhunter).

POST /api/outreach/headhunter
    Shortcut for headhunter-type messages; pre-fills common agency fields.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.outreach_service import generate_outreach_message

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
async def generate_message(body: OutreachRequest) -> OutreachResponse:
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
async def generate_headhunter_message(body: HeadhunterRequest) -> OutreachResponse:
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
        )
    except Exception as exc:
        logger.exception("[outreach] Headhunter message generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return OutreachResponse(
        message_type = "headhunter",
        message      = message,
        word_count   = len(message.split()),
    )
