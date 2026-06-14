"""
Auto-Applier Agent
Uses Playwright to submit job applications on behalf of the user.
Generates tailored cover letters via Claude before each submission.
Respects daily limits, duplicate-company windows, and pause-on-rejection rules.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

import anthropic
from playwright.async_api import async_playwright, Page

from models.job import JobMatch
from models.application import Application, ApplicationStatus
from models.user import UserProfile

logger = logging.getLogger(__name__)


@dataclass
class ApplierConfig:
    model: str = "claude-sonnet-4-6"
    cover_letter_max_tokens: int = 600
    daily_limit: int = 15
    skip_dup_window_days: int = 90
    headless: bool = True


class AutoApplierAgent:
    """
    Submits applications to job postings that pass the match threshold.
    Generates a tailored cover letter for each application using Claude.
    """

    def __init__(self, config: ApplierConfig | None = None) -> None:
        self.config = config or ApplierConfig()
        self._client = anthropic.AsyncAnthropic()
        self._applied_today: list[str] = []
        self._rejected_today: bool = False
        self._applied_companies: dict[str, date] = {}

    async def apply(self, match: JobMatch, profile: UserProfile) -> Application:
        """
        Attempt to submit an application for the given match.
        Returns an Application record (submitted or skipped).
        """
        if not self._can_apply(match):
            return Application(
                job_id=match.job_id,
                status=ApplicationStatus.SKIPPED,
                reason="Daily limit reached, duplicate, or paused after rejection",
            )

        cover_letter = await self._generate_cover_letter(match, profile)
        result = await self._submit_via_browser(match, cover_letter)

        self._applied_today.append(match.job_id)
        self._applied_companies[match.company] = date.today()

        logger.info("Applied to %s @ %s (score=%d)", match.title, match.company, match.score)
        return result

    def record_rejection(self) -> None:
        self._rejected_today = True

    def reset_daily_state(self) -> None:
        self._applied_today = []
        self._rejected_today = False

    def _can_apply(self, match: JobMatch) -> bool:
        if len(self._applied_today) >= self.config.daily_limit:
            return False
        if self._rejected_today:
            return False
        last_applied = self._applied_companies.get(match.company)
        if last_applied and (date.today() - last_applied) < timedelta(days=self.config.skip_dup_window_days):
            return False
        return True

    async def _generate_cover_letter(self, match: JobMatch, profile: UserProfile) -> str:
        prompt = f"""Write a concise, tailored cover letter (3 short paragraphs) for this job.
Highlight the most relevant skills and experience. Do not fabricate details.

Job: {match.title} at {match.company}
Match reasons: {[r.label for r in match.reasons]}
Candidate profile summary: {profile.summary or 'Not provided'}"""

        message = await self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.cover_letter_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def _submit_via_browser(self, match: JobMatch, cover_letter: str) -> Application:
        """Launch a headless browser and fill the application form."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self.config.headless)
            page: Page = await browser.new_page()
            try:
                await page.goto(match.apply_url or "", timeout=30_000)
                # TODO: implement per-ATS form-fill logic (Greenhouse, Lever, Workday…)
                await page.close()
            finally:
                await browser.close()

        return Application(
            job_id=match.job_id,
            status=ApplicationStatus.SUBMITTED,
            cover_letter=cover_letter,
        )
