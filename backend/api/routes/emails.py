"""
Inbound email webhook — receives parsed recruiter emails and updates the
application pipeline automatically.

POST /api/webhooks/inbound-email
  Body: { "sender": str, "subject": str, "body_text": str }

Flow
----
0. [NEW] Check for Gmail forwarding verification email FIRST.
   If sender is forwarding-noreply@google.com or subject contains
   "Gmail Forwarding Confirmation", extract the 9-digit confirmation
   code and persist it in the kv_store table, then return early.
1. Validate the payload.
2. Call email_parser.parse_recruiter_email() to extract company + status.
3. If mapped_status == "Unknown", return early (no DB mutation).
4. Search ApplicationRow for a matching company that is still in a
   non-terminal stage.  Match is case-insensitive and substring-based
   so "Wix Engineering" matches a stored company of "Wix".
5. If a match is found, update its status and last_update timestamp.
6. Return a structured response describing what happened.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.db import ENGINE, ApplicationRow, KVRow
from services.email_parser import parse_recruiter_email

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Gmail verification intercept ──────────────────────────────────────────────
# Google sends a forwarding confirmation email whose subject is always
# "Gmail Forwarding Confirmation - Receive Mail from <address>"
# and whose sender is forwarding-noreply@google.com.
# The body contains a 9-digit confirmation code on its own line, e.g.:
#   "Confirmation code: 123456789"  or  just  "123456789" on an isolated line.

_GMAIL_SENDERS   = frozenset({"forwarding-noreply@google.com"})
_GMAIL_SUBJ_FRAG = "gmail forwarding confirmation"
_KV_CODE_KEY     = "gmail_verification_code"

# Two patterns — prefer the labelled one, fall back to any isolated 9-digit run.
_CODE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'(?i)confirmation\s+code[:\s]+(\d{9})\b'),
    re.compile(r'\b(\d{9})\b'),
]


def _extract_gmail_code(body: str) -> Optional[str]:
    """Return the first 9-digit confirmation code found in the email body."""
    for pattern in _CODE_PATTERNS:
        m = pattern.search(body)
        if m:
            return m.group(1)
    return None


def _is_gmail_verification(sender: str, subject: str) -> bool:
    """True when the email is a Gmail forwarding confirmation."""
    return (
        sender.strip().lower() in _GMAIL_SENDERS
        or _GMAIL_SUBJ_FRAG in subject.strip().lower()
    )


def _store_gmail_code(code: str) -> None:
    """Upsert the verification code into the kv_store table."""
    now = datetime.now(timezone.utc).isoformat()
    with Session(ENGINE) as db:
        row = db.get(KVRow, _KV_CODE_KEY)
        if row:
            row.value      = code
            row.updated_at = now
        else:
            db.add(KVRow(key=_KV_CODE_KEY, value=code, updated_at=now))
        db.commit()
    logger.info("[email-webhook] Stored Gmail verification code=%r", code)


# ── Stages that a company can be moved OUT of via an inbound email ────────────
# We don't overwrite an already-final status (offer / rejected) with a new
# classification — that would be destructive and probably an error.
_UPDATABLE_STATUSES: frozenset[str] = frozenset({
    "submitted",
    "phone screen",
    "technical",
    "interview",
})


# ── Pydantic models ────────────────────────────────────────────────────────────

class InboundEmailPayload(BaseModel):
    sender:    str
    subject:   str
    body_text: str


class EmailWebhookResponse(BaseModel):
    received:      bool
    company_name:    Optional[str]
    mapped_status:   str
    db_status:       Optional[str]
    match_found:     bool
    application_id:  Optional[str]
    previous_status: Optional[str]
    action:          str           # "updated" | "skipped" | "no_match" | "gmail_verification"
    verification_code: Optional[str] = None  # populated when action == "gmail_verification"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _find_application(
    session: Session,
    company_name: str,
) -> ApplicationRow | None:
    """
    Return the most-recently-submitted application whose company name
    fuzzy-matches `company_name` AND whose status is still updatable.

    Matching strategy (both directions of substring):
      • DB row "Wix"          matches extracted "Wix Engineering"
      • DB row "Google Inc."  matches extracted "Google"
    This covers the most common formatting mismatches without a full
    fuzzy-similarity library.
    """
    candidates: list[ApplicationRow] = (
        session.query(ApplicationRow)
        .filter(ApplicationRow.status.in_(_UPDATABLE_STATUSES))
        .order_by(ApplicationRow.submitted_at.desc())
        .all()
    )

    company_lower = company_name.strip().lower()
    for row in candidates:
        row_company = (row.company or "").strip().lower()
        if company_lower in row_company or row_company in company_lower:
            return row

    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── Webhook endpoint ───────────────────────────────────────────────────────────

@router.post("/inbound-email", response_model=EmailWebhookResponse)
async def inbound_email_webhook(payload: InboundEmailPayload) -> EmailWebhookResponse:
    """
    Receive a recruiter email, classify it with AI, and update the
    application pipeline if a matching application is found.
    """
    logger.info(
        "[email-webhook] received  sender=%r  subject=%r",
        payload.sender, payload.subject[:80],
    )

    # ── Step 0: Gmail forwarding verification intercept ───────────────────────
    # Must run BEFORE the AI parser — verification emails contain no job data.
    if _is_gmail_verification(payload.sender, payload.subject):
        code = _extract_gmail_code(payload.body_text)
        if code:
            _store_gmail_code(code)
            return EmailWebhookResponse(
                received          = True,
                company_name      = None,
                mapped_status     = "gmail_verification",
                db_status         = None,
                match_found       = False,
                application_id    = None,
                previous_status   = None,
                action            = "gmail_verification",
                verification_code = code,
            )
        else:
            logger.warning(
                "[email-webhook] Gmail verification email received but no 9-digit code found"
            )
            return EmailWebhookResponse(
                received       = True,
                company_name   = None,
                mapped_status  = "gmail_verification",
                db_status      = None,
                match_found    = False,
                application_id = None,
                previous_status= None,
                action         = "skipped",
            )

    # ── Step 1: AI classification ─────────────────────────────────────────────
    parsed = await parse_recruiter_email(
        subject=payload.subject,
        body=payload.body_text,
    )

    company_name  = parsed["company_name"]
    mapped_status = parsed["mapped_status"]
    db_status     = parsed["db_status"]

    # ── Step 2: Early-exit for Unknown or missing company ────────────────────
    if mapped_status == "Unknown" or not company_name or not db_status:
        logger.info(
            "[email-webhook] status=Unknown or unidentifiable company — no DB mutation",
        )
        return EmailWebhookResponse(
            received       = True,
            company_name   = company_name,
            mapped_status  = mapped_status,
            db_status      = db_status,
            match_found    = False,
            application_id = None,
            previous_status= None,
            action         = "skipped",
        )

    # ── Step 3: Find matching application and update ─────────────────────────
    with Session(ENGINE) as session:
        row = _find_application(session, company_name)

        if row is None:
            logger.info(
                "[email-webhook] no updatable application found for company=%r", company_name,
            )
            return EmailWebhookResponse(
                received       = True,
                company_name   = company_name,
                mapped_status  = mapped_status,
                db_status      = db_status,
                match_found    = False,
                application_id = None,
                previous_status= None,
                action         = "no_match",
            )

        previous_status  = row.status
        row.status       = db_status
        row.last_update  = _now_iso()
        application_id   = row.application_id
        session.commit()

    logger.info(
        "[email-webhook] updated application_id=%r  company=%r  %r → %r",
        application_id, company_name, previous_status, db_status,
    )

    return EmailWebhookResponse(
        received        = True,
        company_name    = company_name,
        mapped_status   = mapped_status,
        db_status       = db_status,
        match_found     = True,
        application_id  = application_id,
        previous_status = previous_status,
        action          = "updated",
    )
