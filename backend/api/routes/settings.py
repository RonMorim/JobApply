from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import CurrentUser, get_current_user, require_admin
from backend.services.db import ENGINE, KVRow

router = APIRouter()

# ── LinkedIn scraper status endpoint ─────────────────────────────────────────

_KV_SCRAPER_STATUS = "linkedin_scraper_status"
_KV_BLOCKED_AT     = "linkedin_scraper_blocked_at"
_KV_COOKIE_STATUS  = "linkedin_cookie_status"
_KV_SCRAPER_PAUSED = "linkedin_scraper_paused"


class ScraperStatusResponse(BaseModel):
    status:        str            # 'ok' | 'suspicious' | 'BLOCKED' | 'PAUSED'
    blocked_at:    Optional[str]  # ISO-8601 UTC, set when status='BLOCKED'
    cookie_status: Optional[str]  # 'ok' | 'suspicious'


@router.get("/scraper-status", response_model=ScraperStatusResponse)
async def get_scraper_status(user: CurrentUser = Depends(get_current_user)) -> ScraperStatusResponse:
    """
    Return the current LinkedIn scraper health status.

    Reads four KV keys:
      • linkedin_scraper_status  — 'BLOCKED' when redirect-loop threshold hit
      • linkedin_scraper_blocked_at — ISO timestamp when BLOCKED was set
      • linkedin_cookie_status   — 'suspicious' after first redirect error
      • linkedin_scraper_paused  — '1' when manually paused via reset script

    Priority: BLOCKED > PAUSED > suspicious > ok.
    Returns status='ok' when no errors have been recorded.
    """
    with Session(ENGINE) as db:
        status_row = db.get(KVRow, _KV_SCRAPER_STATUS)
        blocked_row = db.get(KVRow, _KV_BLOCKED_AT)
        cookie_row  = db.get(KVRow, _KV_COOKIE_STATUS)
        paused_row  = db.get(KVRow, _KV_SCRAPER_PAUSED)

    blocked_at    = blocked_row.value if blocked_row else None
    cookie_status = cookie_row.value  if cookie_row  else "ok"

    if status_row and status_row.value == "BLOCKED":
        status = "BLOCKED"
    elif paused_row and paused_row.value == "1":
        # Manually paused via reset_linkedin_scraper.py --pause while a fresh
        # cookie is being configured.  Distinct from BLOCKED so the UI can show
        # a maintenance message instead of an error banner.
        status = "PAUSED"
    else:
        status = "ok"

    return ScraperStatusResponse(
        status=status,
        blocked_at=blocked_at,
        cookie_status=cookie_status,
    )

# ── Gmail verification code endpoint ─────────────────────────────────────────

_KV_CODE_KEY = "gmail_verification_code"
_CODE_TTL_MINUTES = 30  # discard codes older than this


class GmailVerificationCodeResponse(BaseModel):
    code:       Optional[str]   # None when no code available or TTL expired
    captured_at: Optional[str]  # ISO-8601 UTC timestamp when it was stored


@router.get("/gmail-verification-code", response_model=GmailVerificationCodeResponse)
async def get_gmail_verification_code(user: CurrentUser = Depends(require_admin)) -> GmailVerificationCodeResponse:
    """
    Return the most recently captured Gmail forwarding verification code.

    The webhook (POST /api/webhooks/inbound-email) stores the code when it
    detects a forwarding-noreply@google.com email.  The frontend modal polls
    this endpoint so the code can be displayed automatically.

    Returns code=None when:
      • No code has been captured yet, OR
      • The stored code is older than 30 minutes (stale/already used).
    """
    with Session(ENGINE) as db:
        row = db.get(KVRow, _KV_CODE_KEY)

    if row is None:
        return GmailVerificationCodeResponse(code=None, captured_at=None)

    # TTL check — codes older than _CODE_TTL_MINUTES are silently expired
    try:
        stored_at = datetime.fromisoformat(row.updated_at)
        age = datetime.now(timezone.utc) - stored_at.astimezone(timezone.utc)
        if age > timedelta(minutes=_CODE_TTL_MINUTES):
            return GmailVerificationCodeResponse(code=None, captured_at=None)
    except (ValueError, TypeError):
        # Malformed timestamp — treat as expired
        return GmailVerificationCodeResponse(code=None, captured_at=None)

    return GmailVerificationCodeResponse(code=row.value, captured_at=row.updated_at)
