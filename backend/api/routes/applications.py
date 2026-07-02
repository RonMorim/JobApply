from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import CurrentUser, get_current_user
from models.application import Application, ApplicationStatus
from backend.services import app_store, job_store
from backend.services.db import ENGINE, ApplicationRow, JobRow

logger = logging.getLogger(__name__)

router = APIRouter()


class RunCycleResponse(BaseModel):
    submitted: int
    applications: list[Application]


@router.get("/", response_model=list[Application])
async def list_applications(user: CurrentUser = Depends(get_current_user)):
    """Return all submitted applications for the authenticated user, most recent first."""
    return app_store.get_all(user_id=user.user_id)


@router.post("/run", response_model=RunCycleResponse)
async def run_applier_cycle(
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Trigger the ApplierAgent cycle synchronously.
    Finds all jobs with score >= 85 that haven't been applied to yet,
    submits simulated applications, and returns the results.
    """
    from backend.agents.applier import ApplierAgent
    agent   = ApplierAgent(user_id=user.user_id)
    results = await asyncio.to_thread(agent.run_cycle)
    logger.info("[api/applications] run_cycle completed — %d submitted", len(results))
    return RunCycleResponse(submitted=len(results), applications=results)


@router.post("/{job_id}/apply", response_model=Application)
async def apply_to_job(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Manually trigger an application for a specific job."""
    from backend.agents.applier import ApplierAgent
    app = await asyncio.to_thread(ApplierAgent(user_id=user.user_id).apply_single, job_id)
    if app is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found or has already been applied to.",
        )
    return app


@router.get("/{application_id}", response_model=Application)
async def get_application(
    application_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Return a single application by ID, scoped to the authenticated user."""
    all_apps = app_store.get_all(user_id=user.user_id)
    match    = next((a for a in all_apps if a.application_id == application_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return match


# ── Mark as Applied — explicit user action ────────────────────────────────────

class MarkAppliedRequest(BaseModel):
    job_id: str


class MarkAppliedResponse(BaseModel):
    application_id: str
    job_id:         str
    company:        str
    title:          str
    status:         str
    created:        bool   # True = new record; False = record already existed


@router.post("/mark-applied", response_model=MarkAppliedResponse)
async def mark_applied(
    body: MarkAppliedRequest,
    user: CurrentUser = Depends(get_current_user),
) -> MarkAppliedResponse:
    """
    Explicitly record that the user submitted their tailored CV for a job.

    - Looks up the JobRow to get company/title/score.
    - Checks whether an ApplicationRow already exists for this job.
      If yes → updates status to 'submitted' and returns it.
      If no  → creates a new ApplicationRow with status='submitted'.
    - Marks JobRow.applied = True and sets applied_at timestamp.

    This is the canonical action that moves a job card into the Kanban pipeline.
    Calling /tailor-cv does NOT trigger this — the user must explicitly click
    "Mark as Applied" to confirm they sent the CV.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with Session(ENGINE) as db:
        # ── Verify job exists ─────────────────────────────────────────────────
        job_row = db.get(JobRow, body.job_id)
        if not job_row:
            raise HTTPException(
                status_code=404,
                detail=f"Job '{body.job_id}' not found.",
            )

        company = job_row.company or ""
        title   = job_row.title   or ""
        score   = float(job_row.score or 0.0)

        # ── Upsert ApplicationRow ─────────────────────────────────────────────
        existing = (
            db.query(ApplicationRow)
            .filter(
                ApplicationRow.job_id  == body.job_id,
                ApplicationRow.user_id == user.user_id,
            )
            .first()
        )

        if existing:
            # Already in the pipeline — ensure status is at least 'submitted'
            # but do not downgrade a card that has already advanced.
            already_advanced = existing.status not in ("", None)
            if not already_advanced or existing.status == "submitted":
                existing.status      = "submitted"
                existing.last_update = now_str
            application_id = existing.application_id
            created        = False
        else:
            application_id = str(uuid.uuid4())
            new_row = ApplicationRow(
                application_id = application_id,
                user_id        = user.user_id,
                job_id         = body.job_id,
                title          = title,
                company        = company,
                ats            = "Direct",
                status         = "submitted",
                submitted_at   = now_str,
                last_update    = now_str,
                score          = score,
            )
            db.add(new_row)
            created = True

        # ── Mark job as applied ───────────────────────────────────────────────
        job_row.applied    = True
        job_row.applied_at = now_str
        job_row.status     = "applied"   # feed-level status

        db.commit()

    logger.info(
        "[applications/mark-applied] job=%s → application=%s  created=%s",
        body.job_id, application_id, created,
    )
    return MarkAppliedResponse(
        application_id = application_id,
        job_id         = body.job_id,
        company        = company,
        title          = title,
        status         = "submitted",
        created        = created,
    )
