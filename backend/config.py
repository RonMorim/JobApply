"""
Operational configuration constants for the JobApply backend.

All flags that control cost, frequency, or external-API usage live here so
they can be found and changed in one place before launch.
"""

# ── Targeted search queries ───────────────────────────────────────────────────
# The canonical list of job-title search terms used by every scraper and the
# discovery pipeline.  Scrapers submit one search request per term; the
# relevancy gate in backend/scrapers/relevancy.py also derives its matching
# rules from this list.
#
# Guidelines:
#   • Use full role titles — the gate checks for substring presence.
#   • Include Hebrew variants for Israeli boards (Drushim, AllJobs, etc.).
#   • Keep the list focused: each extra entry multiplies HTTP requests across
#     all board scrapers.
TARGET_SEARCH_QUERIES: list[str] = [
    # ── Product Management (English) ──────────────────────────────────────────
    "Product Manager",
    "Product Owner",
    "Group Product Manager",
    "Senior Product Manager",
    "Head of Product",
    "VP Product",
    "Director of Product",
    "Product Operations Manager",
    "Product Lead",
    "Product Management",
    # ── Product Management (Hebrew) ───────────────────────────────────────────
    "מנהל מוצר",
    "מנהלת מוצר",
    # ── Customer Success & Account Management (English) ───────────────────────
    "Customer Success",
    "CSM",
    "Account Manager",
    "Key Account Manager",
    "Partnership Manager",
    # ── Customer Success & Account Management (Hebrew) ────────────────────────
    "מנהל הצלחת לקוחות",
    "מנהלת הצלחת לקוחות",
    "מנהל תיקי לקוחות",
    "מנהלת תיקי לקוחות",
]

# ── Per-run discovery cap ─────────────────────────────────────────────────────
# Maximum number of *new* relevant jobs to persist in a single discovery run
# (shared across all scrapers / queries).  Pagination halts immediately once
# this cap is reached so no further HTTP or LLM credits are spent.
MAX_RELEVANT_JOBS: int = 50

# ── Auto-discovery toggle ─────────────────────────────────────────────────────
# Master switch for the background discovery loop.
# Keep False until single-job manual analysis (POST /api/jobs/analyze) is
# confirmed flawless end-to-end.  Set True to re-enable batch discovery.
#
# When False the _discovery_loop() in main.py logs a warning and sleeps
# indefinitely — no LinkedIn searches, no DB writes, no LLM calls.
AUTO_DISCOVERY: bool = True

# ── Credit conservation ───────────────────────────────────────────────────────
# When True, all automatic JD-text scraping is suppressed.
# The discovery loop will still run and ingest job metadata (title, company,
# URL) but will NOT call fetch_descriptions=True on the LinkedIn scraper.
# Full JD content is only retrieved when the user explicitly clicks
# "Fetch Missing Details" or opens a card that triggers an inline fetch.
#
# TODO: RE-ENABLE HIGH-FREQUENCY POLLING BEFORE LAUNCH.
#       Set CREDIT_CONSERVATION_MODE = False and review DISCOVERY_INTERVAL_SECONDS.
CREDIT_CONSERVATION_MODE: bool = True

# ── Discovery loop interval ───────────────────────────────────────────────────
# How often (in seconds) the background discovery loop runs.
#
# Pre-launch value  : 300   (5 minutes)  — uncomment after credit budget is set
# Conservation value: 86400 (24 hours)   — active while CREDIT_CONSERVATION_MODE=True
#
# TODO: RE-ENABLE HIGH-FREQUENCY POLLING BEFORE LAUNCH.
#       Switch back to DISCOVERY_INTERVAL_SECONDS = 300.
DISCOVERY_INTERVAL_SECONDS: int = 86400  # 24 hours — credit-conservation mode

# ── Development mode ──────────────────────────────────────────────────────────
# When DEV_MODE is True, each board scraper is capped at DEV_MAX_JOBS_PER_BOARD
# detail-page fetches per run.  This keeps the full s1 → s4 pipeline cycle
# under ~30 seconds locally instead of several minutes.
#
# !! SET DEV_MODE = False BEFORE DEPLOYING TO PRODUCTION !!
#
# Guidance:
#   DEV_MAX_JOBS_PER_BOARD = 3   → ultra-fast (~5 s); good for UI transition tests
#   DEV_MAX_JOBS_PER_BOARD = 5   → fast  (~10 s); enough real data to inspect scores
#   DEV_MAX_JOBS_PER_BOARD = 15  → moderate; good for scoring / backfill accuracy checks
DEV_MODE: bool = False
DEV_MAX_JOBS_PER_BOARD: int = 5

# ── LinkedIn authenticated scraping ───────────────────────────────────────────
# Optional session cookie used by the LinkedIn JD scraper to bypass the login
# wall on `il.linkedin.com` job pages.
#
# How to obtain:
#   1. Log in to linkedin.com in a desktop browser.
#   2. Open DevTools → Application → Cookies → www.linkedin.com
#   3. Copy the value of the `li_at` cookie.
#   4. Add to backend/.env:  LINKEDIN_LI_AT=<paste value here>
#
# Security: treat this value like a password — do NOT commit it to version
# control or expose it in logs.  The scraper never logs the cookie value.
#
# When None (default), the scraper falls back to unauthenticated requests
# (which LinkedIn rate-limits and blocks for most job pages).
import os as _os
from typing import Optional as _Optional
LINKEDIN_LI_AT: _Optional[str] = _os.environ.get("LINKEDIN_LI_AT") or None
