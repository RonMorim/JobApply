"""
URL Router — maps a job posting URL to the correct scraper.

Two public entry points:

1.  scrape_jd_text(url: str) -> str
    Fetches and returns the full JD text for a single job URL.
    Routes to a site-specific parser when available; falls back to the
    generic url_scraper.scrape_job_post() for unknown hosts.
    Used by:
      - backend.api.routes.jobs  → POST /{job_id}/fetch-jd
      - backend.services.jd_backfill_service → backfill_jd_text()

2.  get_scraper_for_url(url: str) -> Optional[BaseScraper]
    Returns a BaseScraper instance capable of calling fetch_jobs() for
    the host found in `url`.  Useful for one-shot scraping of a specific
    source URL without going through ScraperManager.
    Returns None for unknown hosts.

Domain routing table
--------------------
linkedin.com         → _linkedin_scrape_async (authenticated, persistent context)
                         • LINKEDIN_LI_AT set → Playwright persistent context (JS SPA)
                         • LINKEDIN_LI_AT absent → requests + BeautifulSoup (login wall only)
gotfriends.co.il     → scrape_gotfriends_jd
dialog.co.il         → scrape_dialog_jd
nisha.co.il          → scrape_nisha_jd
alljobs.co.il        → scrape_alljobs_jd
comeet.co / .com     → generic (Comeet pages render server-side, generic works)
<everything else>    → generic scrape_job_post

LinkedIn authentication — Persistent Context
---------------------------------------------
LinkedIn renders all JD text via React (SPA).  The static HTML shell returned
by requests.get() contains only the page frame, not the JD body.

When LINKEDIN_LI_AT is set the scraper uses a **persistent browser context**
(launch_persistent_context) that writes cookies, localStorage, and IndexedDB
to disk at _LINKEDIN_USER_DATA_DIR.  This gives the browser a real identity
that "wears in" over time rather than appearing as a fresh bot session on
every request.

Session lifecycle
-----------------
  • One persistent context is shared for the lifetime of the process.
  • The li_at cookie is injected on first launch and verified before every
    scrape.  If the cookie is absent the context is no longer authenticated.
  • A warm-up navigation (linkedin.com/feed → random scroll → jitter) runs
    once when the context is first created so the very first job URL is never
    the browser's first LinkedIn request.
  • AUTH_WALL detection:  if the page title or a prominent heading signals a
    login wall, LinkedInAuthWallError is raised instead of ValueError.
    Callers (hydrate_job) must route AUTH_WALL to status='auth_wall', NOT
    'failed', and must NOT increment enrichment_failures.

Concurrency
-----------
  asyncio.Semaphore(2) caps simultaneous pages inside the shared context to
  limit memory.  An asyncio.Lock serialises context init (double-checked).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from backend.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# ── Auth-wall sentinel exception ─────────────────────────────────────────────
# Raised by _linkedin_scrape_async when the page is a LinkedIn login wall.
# Distinct from ValueError (generic scraper failure) so callers can route
# these to a separate 'auth_wall' status rather than incrementing
# enrichment_failures and eventually retiring the job as 'failed'.

class LinkedInAuthWallError(Exception):
    """LinkedIn returned a login/authwall page — cookie may be expired."""

class LinkedInRedirectError(Exception):
    """
    LinkedIn navigation hit ERR_TOO_MANY_REDIRECTS — a strong bot-detection
    signal.  Raised instead of a generic error so callers can:
      • Immediately stop retrying the job (don't burn enrichment_failures).
      • Increment a process-level redirect-error counter.
      • Set linkedin_scraper_status='BLOCKED' in the KV store after 2 hits.
    """

# ── Persistent context storage ───────────────────────────────────────────────
# Chromium writes cookies, localStorage, IndexedDB, and cache here.
# The directory persists across process restarts so the session "wears in"
# and LinkedIn sees a browser with genuine history, not a fresh bot each time.
_LINKEDIN_USER_DATA_DIR = Path(
    os.environ.get(
        "LINKEDIN_USER_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "linkedin_browser_profile"),
    )
)

# ── LinkedIn JD extraction ────────────────────────────────────────────────────

# Minimum chars we consider a real JD (mirrors feed_service._JD_MIN_CHARS).
_LI_MIN_CHARS = 250

# UI boilerplate injected by LinkedIn's login wall, cookie banner, and
# surrounding chrome.  Both English and Hebrew variants are included since
# the scraper targets Israeli job listings.
_LINKEDIN_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"Agree\s*&\s*Join\s*LinkedIn",
        r"Sign\s+in\s+to\s+(?:view|see|access|apply|create\s+(?:a\s+)?job\s+alert)",
        r"Join\s+to\s+apply",
        r"Join\s+now",
        r"Cookie\s+Policy",
        r"Privacy\s+Policy",
        r"User\s+Agreement",
        r"See\s+more\s+jobs",
        r"Show\s+more",
        r"Show\s+less",
        r"Get\s+notified\s+about\s+new",
        r"Be\s+an\s+early\s+applicant",
        r"Actively\s+Hiring",
        r"Easy\s+Apply",
        r"Save\s+this\s+job",
        r"Report\s+this\s+job",
        r"Dismiss",
        r"Submit\s+application",
        r"Back\s+to\s+job\s+search",
        r"Similar\s+jobs",
        r"People\s+also\s+viewed",
        r"You\s+may\s+also\s+like",
        r"Set\s+alert\s+for\s+similar\s+jobs",
        # Hebrew boilerplate
        r"להגיש\s+מועמדות",      # "Submit application"
        r"הסכמה\s+והצטרפות",    # "Agree & Join"
        r"מדיניות\s+עוגיות",    # "Cookie Policy"
        r"ראה\s+עוד",            # "See more"
        r"הצג\s+פחות",           # "Show less"
        r"התחבר\s+כדי\s+לצפות", # "Sign in to view"
    ]
]

# Noise phrases that, when present in high density, indicate the page is a
# login wall rather than a real JD.  If ≥ 3 are found the text is rejected.
_LOGINWALL_SIGNALS = [
    "sign in", "join linkedin", "cookie policy", "agree & join",
    "create an account", "join now",
]


def _clean_linkedin_text(raw: str) -> str:
    """
    Strip LinkedIn UI boilerplate from extracted text and normalise whitespace.

    Applies _LINKEDIN_NOISE_PATTERNS line by line, drops empty/short remnants,
    then collapses duplicate blank lines.
    """
    for pattern in _LINKEDIN_NOISE_PATTERNS:
        raw = pattern.sub("", raw)

    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if len(line) > 2:          # discard single chars / punctuation fragments
            lines.append(line)

    return "\n".join(lines)


def _is_loginwall(text: str) -> bool:
    """
    Return True when the cleaned text is dominated by login-wall boilerplate
    rather than real JD content.  Triggered when ≥ 3 loginwall signals appear.
    """
    lower = text.lower()
    hits  = sum(1 for sig in _LOGINWALL_SIGNALS if sig in lower)
    return hits >= 3


# ── Per-site JD scrapers ──────────────────────────────────────────────────────
# Each entry is (domain_suffix, jd_scrape_fn).
# Matched against the URL hostname with endswith() so "www.gotfriends.co.il"
# and "gotfriends.co.il" both hit the same handler.

def _generic_scrape(url: str) -> str:
    from backend.url_scraper import scrape_job_post
    scraped = scrape_job_post(url)
    return scraped.raw_text


# ── LinkedIn request rate-limiter ────────────────────────────────────────────
# hydrate_job() fires all 367 scrapes concurrently via asyncio.gather; each
# runs in its own thread via asyncio.to_thread.  Without throttling, LinkedIn
# returns HTTP 429 (Request denied) after a burst of ~10 requests.
#
# Strategy: serialise LinkedIn HTTP calls behind a lock and enforce a minimum
# inter-request interval.  0.8 s base + 0–0.4 s jitter ≈ 1–2 req/s, which
# sits comfortably under LinkedIn's observed rate limit.
#
# Note: the lock also prevents the "thundering herd" — all 367 threads waking
# simultaneously.  Thread that acquires the lock sleeps for the remaining wait
# time before releasing, so the next thread waits its turn.
_LINKEDIN_RATE_LOCK      = threading.Lock()
_LINKEDIN_LAST_REQ_TIME  = 0.0            # epoch seconds of last completed request
_LINKEDIN_MIN_INTERVAL   = 0.8            # base seconds between requests
_LINKEDIN_JITTER         = 0.4            # additional random jitter (0 – 0.4 s)


def _linkedin_rate_wait() -> None:
    """Block the calling thread until it is safe to fire the next LinkedIn request."""
    global _LINKEDIN_LAST_REQ_TIME
    with _LINKEDIN_RATE_LOCK:
        now    = time.time()
        gap    = _LINKEDIN_MIN_INTERVAL + random.uniform(0, _LINKEDIN_JITTER)
        since  = now - _LINKEDIN_LAST_REQ_TIME
        if since < gap:
            time.sleep(gap - since)
        _LINKEDIN_LAST_REQ_TIME = time.time()


_LINKEDIN_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.7151.55 Safari/537.36"
)

# Full browser-grade header set sent on every LinkedIn request.
# Authenticated sessions (li_at cookie present) use the same headers —
# the cookie is injected separately so headers stay constant.
_LINKEDIN_HEADERS: dict[str, str] = {
    "User-Agent":                _LINKEDIN_UA,
    "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":           "en-US,en;q=0.9",
    "Accept-Encoding":           "gzip, deflate, br",
    "Referer":                   "https://www.linkedin.com/jobs/",
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "same-origin",
    "Sec-CH-UA":                 '"Chromium";v="137", "Google Chrome";v="137", "Not-A.Brand";v="24"',
    "Sec-CH-UA-Mobile":          "?0",
    "Sec-CH-UA-Platform":        '"macOS"',
    "Upgrade-Insecure-Requests": "1",
    "Connection":                "keep-alive",
}


# ── Async Playwright scraper (LinkedIn SPA) ───────────────────────────────────
# LinkedIn renders all JD text via React (SPA).  requests.get() returns only
# the static HTML shell even with the li_at session cookie.
#
# Architecture:
#   • async_playwright — runs natively on the asyncio event loop, eliminating
#     the greenlet.error caused by the Playwright sync API inside to_thread().
#   • One shared Chromium browser process per event loop (lazy-init).
#   • Per-request BrowserContext + Page — no shared mutable state.
#   • asyncio.Semaphore(3) caps active page sessions to bound memory usage.
#   • Async rate limiter serialises navigation starts (0.8 s + 0–0.4 s jitter).

# LinkedIn changes its CSS class names frequently.  Try these selectors in
# order; the first one that yields ≥ _LI_MIN_CHARS of non-loginwall text wins.
# Add new candidates at the front when LinkedIn ships a markup update.
_PLAYWRIGHT_JD_SELECTORS: list[str] = [
    # 2024-2025 layout
    ".jobs-description__content",
    ".jobs-description",
    # Older layout (pre-2024)
    ".jobs-description-content__text",
    # Generic fallbacks
    "div[class*='description__text']",
    "div[class*='jobs-description']",
    "article",                          # last resort — broad but often works
]

# ── Async rate limiter ────────────────────────────────────────────────────────
# Guards the persistent-context path.  Even though we share one context,
# we still throttle individual page navigations to avoid triggering LinkedIn's
# rate-limiting heuristics when processing large batches of jobs.
_ARATE_LOCK:      Optional[asyncio.Lock] = None
_ARATE_LAST_TIME: float = 0.0


def _ensure_arate_lock() -> asyncio.Lock:
    global _ARATE_LOCK
    if _ARATE_LOCK is None:
        _ARATE_LOCK = asyncio.Lock()
    return _ARATE_LOCK


async def _linkedin_arate_wait() -> None:
    """Async rate-limiter gate — enforces minimum gap between LinkedIn navigations."""
    global _ARATE_LAST_TIME
    async with _ensure_arate_lock():
        now   = time.time()
        gap   = _LINKEDIN_MIN_INTERVAL + random.uniform(0, _LINKEDIN_JITTER)
        since = now - _ARATE_LAST_TIME
        if since < gap:
            await asyncio.sleep(gap - since)
        _ARATE_LAST_TIME = time.time()


# ── Persistent context singleton ─────────────────────────────────────────────
# One persistent BrowserContext shared for the lifetime of the process.
# launch_persistent_context() stores cookies/localStorage/IndexedDB on disk
# at _LINKEDIN_USER_DATA_DIR so the session survives server restarts.
#
# Semaphore(2): allow at most 2 concurrent pages inside the shared context
# to keep memory bounded.  Higher concurrency is not safe — LinkedIn can
# detect multiple simultaneous requests from the same session fingerprint.

_APW_PLAYWRIGHT: Optional[object]           = None   # async_api.Playwright
_APW_CTX:        Optional[object]           = None   # async_api.BrowserContext (persistent)
_APW_WARMED:     bool                       = False  # True once warm-up nav has completed
_APW_INIT_LOCK:  Optional[asyncio.Lock]     = None
_APW_SEM:        Optional[asyncio.Semaphore]= None


def _ensure_apw_primitives() -> tuple:
    global _APW_INIT_LOCK, _APW_SEM
    if _APW_INIT_LOCK is None:
        _APW_INIT_LOCK = asyncio.Lock()
    if _APW_SEM is None:
        _APW_SEM = asyncio.Semaphore(2)
    return _APW_INIT_LOCK, _APW_SEM


# ── Stealth JS patch ──────────────────────────────────────────────────────────
# Applied to every new page via context.add_init_script() so it fires before
# any page-level JS executes.  This patches all three properties LinkedIn's
# bot-detection script checks on every load, without needing an external package.

_STEALTH_SCRIPT = """
(function () {
    // 1. Remove the webdriver flag
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // 2. Spoof a realistic plugins list (headless Chrome has 0)
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            var arr = [1, 2, 3, 4, 5];
            arr.item = function(i) { return arr[i]; };
            arr.namedItem = function(n) { return null; };
            arr.refresh = function() {};
            return arr;
        }
    });

    // 3. Spoof languages
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

    // 4. Add chrome runtime object expected by Google/LinkedIn scripts
    if (!window.chrome) {
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
    }

    // 5. Spoof permissions API (headless Chrome returns 'denied' for notifications)
    const origQuery = window.navigator.permissions
        ? window.navigator.permissions.query.bind(window.navigator.permissions)
        : null;
    if (origQuery) {
        window.navigator.permissions.query = function(params) {
            return params.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origQuery(params);
        };
    }
})();
"""

_STEALTH_PLAYWRIGHT_TRIED = False


async def _apply_stealth_to_context(ctx) -> None:
    """
    Register the stealth init script on the persistent context so it runs
    automatically on every page created within the context.

    Tries playwright-stealth first; falls back to the manual _STEALTH_SCRIPT.
    playwright-stealth is installed once per context (not per page) because
    add_init_script() on the context object applies to all future pages.
    """
    global _STEALTH_PLAYWRIGHT_TRIED
    if not _STEALTH_PLAYWRIGHT_TRIED:
        _STEALTH_PLAYWRIGHT_TRIED = True
        try:
            from playwright_stealth import stealth_async   # type: ignore
            # playwright-stealth works at the page level; we'll call it per page below.
            # Mark as unavailable for context-level usage.
            logger.info("[linkedin_playwright] playwright-stealth package found — will apply per page")
            return
        except ImportError:
            logger.info("[linkedin_playwright] playwright-stealth not installed — using built-in patch")

    await ctx.add_init_script(_STEALTH_SCRIPT)
    logger.debug("[linkedin_playwright] built-in stealth init script registered on context")


async def _apply_stealth_to_page(page) -> None:
    """Apply playwright-stealth to a single page if available (per-page path)."""
    try:
        from playwright_stealth import stealth_async   # type: ignore
        await stealth_async(page)
    except ImportError:
        pass   # already handled at context level via _STEALTH_SCRIPT


# ── Human behaviour helpers ───────────────────────────────────────────────────

async def _human_jitter(min_ms: int = 800, max_ms: int = 2200) -> None:
    """Sleep for a random interval to mimic human reading/click latency."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _human_scroll(page, min_px: int = 300, max_px: int = 800) -> None:
    """Perform a natural scroll to trigger lazy-loaded content."""
    px = random.randint(min_px, max_px)
    await page.evaluate(f"window.scrollBy(0, {px})")
    await asyncio.sleep(random.uniform(0.3, 0.9))


# ── Auth-wall detection ───────────────────────────────────────────────────────
# LinkedIn shows a login/authwall page when the session cookie is missing or
# expired.  We detect it in three complementary ways so minor layout changes
# don't bypass detection.

_AUTH_WALL_TITLE_KWS = ("sign in", "log in", "join linkedin", "authwall", "checkpoint")
_AUTH_WALL_H1_KWS    = ("sign in", "join linkedin", "create your linkedin account")


async def _detect_auth_wall(page, page_url: str) -> bool:
    """
    Return True if the current page is a LinkedIn login/authwall.

    Checks:
      1. Page title contains a known auth-wall keyword.
      2. The page URL contains /authwall, /login, /checkpoint, or /signup.
      3. The first <h1> text matches an auth-wall phrase.
    """
    title = (await page.title()).lower()
    if any(kw in title for kw in _AUTH_WALL_TITLE_KWS):
        return True

    url_lower = page_url.lower()
    if any(seg in url_lower for seg in ("/authwall", "/login", "/checkpoint", "/signup", "/join")):
        return True

    try:
        h1 = await page.inner_text("h1", timeout=2_000)
        if any(kw in h1.lower() for kw in _AUTH_WALL_H1_KWS):
            return True
    except Exception:
        pass   # no h1 or timeout — not a wall

    return False


# ── Warm-up navigation ────────────────────────────────────────────────────────

async def _warmup(ctx) -> None:
    """
    Navigate to linkedin.com/feed in a temporary page to establish a believable
    browsing history before any job URL is requested.

    This runs once per context lifetime (guarded by _APW_WARMED).
    On auth-wall detection here we log a critical warning — the cookie is
    definitely expired and there is no point continuing.
    """
    global _APW_WARMED
    page = await ctx.new_page()
    try:
        logger.info("[linkedin_playwright] warm-up: navigating to linkedin.com/feed …")
        await page.goto("https://www.linkedin.com/feed/", timeout=30_000, wait_until="domcontentloaded")
        page_url = page.url

        if await _detect_auth_wall(page, page_url):
            logger.critical(
                "[linkedin_playwright] WARM-UP AUTH WALL DETECTED — li_at cookie is "
                "expired or invalid.  Update LINKEDIN_LI_AT in backend/.env and restart. "
                "page_url=%s",
                page_url,
            )
            # We intentionally do NOT raise here — the scraper will raise
            # LinkedInAuthWallError per job.  The critical log is the signal.
        else:
            logger.info("[linkedin_playwright] warm-up: feed loaded OK — url=%s", page_url)

        # Scroll the feed naturally to simulate a human glancing at the page.
        await _human_scroll(page, 200, 600)
        await _human_jitter(3_000, 5_000)   # 3–5 s on the feed page
    finally:
        await page.close()
    _APW_WARMED = True


# ── Persistent context init ───────────────────────────────────────────────────

async def _get_persistent_context(li_at: str):
    """
    Lazy-init and return the shared persistent BrowserContext.

    On first call:
      1. Create _LINKEDIN_USER_DATA_DIR if needed.
      2. launch_persistent_context() → stores session data on disk.
      3. Inject li_at cookie (only if not already present — existing disk
         session may already carry a valid cookie from a prior run).
      4. Register the stealth init script on the context.
      5. Run the warm-up navigation.

    On subsequent calls: return the cached context immediately.
    """
    global _APW_PLAYWRIGHT, _APW_CTX, _APW_WARMED, _STEALTH_PLAYWRIGHT_TRIED

    if _APW_CTX is not None:
        return _APW_CTX

    init_lock, _ = _ensure_apw_primitives()
    async with init_lock:
        if _APW_CTX is not None:
            return _APW_CTX

        from playwright.async_api import async_playwright

        _LINKEDIN_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(
            "[linkedin_playwright] Launching persistent context at %s",
            _LINKEDIN_USER_DATA_DIR,
        )

        pw  = await async_playwright().start()
        ctx = await pw.chromium.launch_persistent_context(
            str(_LINKEDIN_USER_DATA_DIR),
            headless=True,
            user_agent=_LINKEDIN_UA,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
            ],
            extra_http_headers={k: v for k, v in _LINKEDIN_HEADERS.items()
                                if k != "User-Agent"},
        )

        # ── Cookie injection ─────────────────────────────────────────────────
        # Inject li_at only when not already present in the stored profile.
        # A pre-existing cookie means a prior run already established the session.
        existing = {c["name"] for c in await ctx.cookies("https://www.linkedin.com")}
        if "li_at" not in existing:
            await ctx.add_cookies([{
                "name":     "li_at",
                "value":    li_at,
                "domain":   ".linkedin.com",
                "path":     "/",
                "secure":   True,
                "httpOnly": True,
                "sameSite": "None",
            }])
            logger.info("[linkedin_playwright] li_at cookie injected into new persistent context")
        else:
            logger.info("[linkedin_playwright] li_at cookie already present in stored profile — using existing session")

        # ── Stealth: context-level init script ───────────────────────────────
        await _apply_stealth_to_context(ctx)

        _APW_PLAYWRIGHT = pw
        _APW_CTX        = ctx

        # ── Warm-up navigation ───────────────────────────────────────────────
        # Runs in background relative to the init lock so the lock is released
        # before the warm-up page is fully loaded (avoids blocking other callers).
        asyncio.create_task(_warmup(ctx))

    return _APW_CTX


# ── Cookie health check ───────────────────────────────────────────────────────

async def _verify_li_at_cookie(ctx) -> bool:
    """
    Return True if the li_at cookie is present in the persistent context.

    Called before every scrape.  If False, the cookie has been dropped by
    LinkedIn (session invalidated or expired) and every scrape will hit an
    auth wall — we raise LinkedInAuthWallError immediately so the caller can
    halt the enrichment loop rather than burning through retries.
    """
    cookies = await ctx.cookies("https://www.linkedin.com")
    return any(c["name"] == "li_at" for c in cookies)


# ── Main async scraper ────────────────────────────────────────────────────────

async def _linkedin_scrape_async(url: str, li_at: str) -> str:
    """
    Extract LinkedIn JD text using the persistent Chromium context.

    Flow
    ----
    1. Obtain the shared persistent context (lazy-init + warm-up on first call).
    2. Verify li_at cookie is still present.
       → Missing: raise LinkedInAuthWallError (caller sets status='auth_wall').
    3. Enforce rate-limit interval.
    4. Open a new page inside the shared context.
    5. Apply per-page stealth (playwright-stealth if available).
    6. Navigate to the job URL.
    7. Detect auth-wall via title + URL + h1.
       → Auth wall: raise LinkedInAuthWallError.
    8. Scroll + jitter to trigger lazy content.
    9. Try each selector in _PLAYWRIGHT_JD_SELECTORS; accept first ≥ _LI_MIN_CHARS.
    10. Fallback to full body text.

    Raises
    ------
    LinkedInAuthWallError
        Cookie expired / login wall detected.  Caller must NOT increment
        enrichment_failures — this is an infra problem, not a job-data problem.
    ValueError
        Page loaded but no usable JD content found (expired posting, bad URL, etc.).
    """
    ctx = await _get_persistent_context(li_at)
    _, sem = _ensure_apw_primitives()

    # ── Pre-scrape cookie health check ────────────────────────────────────────
    if not await _verify_li_at_cookie(ctx):
        logger.critical(
            "[linkedin_playwright] AUTH WALL — li_at cookie missing from persistent context. "
            "Session expired. Update LINKEDIN_LI_AT in backend/.env and DELETE the "
            "browser profile at %s to force a fresh login. Halting scrape for %s.",
            _LINKEDIN_USER_DATA_DIR, url,
        )
        raise LinkedInAuthWallError(
            "li_at cookie missing from persistent context — session expired. "
            "Refresh LINKEDIN_LI_AT in backend/.env."
        )

    await _linkedin_arate_wait()

    async with sem:
        page = await ctx.new_page()
        try:
            await _apply_stealth_to_page(page)

            # ── Pre-navigation humanized delay ────────────────────────────────
            # Randomised 2–5 s pause before every navigation so LinkedIn's
            # timing heuristics see realistic inter-request gaps.
            pre_delay_ms = random.uniform(2_000, 5_000)
            logger.debug(
                "[linkedin_playwright] Pre-nav delay %.0f ms before %s", pre_delay_ms, url,
            )
            await page.wait_for_timeout(pre_delay_ms)

            logger.debug("[linkedin_playwright] Navigating to %s", url)
            try:
                await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            except Exception as nav_exc:
                err_str = str(nav_exc)
                if "ERR_TOO_MANY_REDIRECTS" in err_str or "Too many redirects" in err_str:
                    logger.error(
                        "[linkedin_playwright] ERR_TOO_MANY_REDIRECTS on %s — "
                        "bot-detection redirect loop.  Raising LinkedInRedirectError "
                        "to halt retries and flag cookie as suspicious.",
                        url,
                    )
                    raise LinkedInRedirectError(
                        f"ERR_TOO_MANY_REDIRECTS on {url} — LinkedIn bot-detection "
                        "redirect loop.  Cookie flagged as suspicious; scraper halted."
                    ) from nav_exc
                raise   # re-raise other navigation errors unchanged

            page_title = await page.title()
            page_url   = page.url

            logger.info(
                "[linkedin_playwright] Landed on: title=%r  url=%s",
                page_title, page_url,
            )

            # ── Auth-wall detection (three complementary checks) ──────────────
            if await _detect_auth_wall(page, page_url):
                logger.error(
                    "[linkedin_playwright] AUTH WALL after navigation — title=%r url=%s. "
                    "Cookie may have been invalidated mid-session. "
                    "Raising LinkedInAuthWallError (job will NOT be marked failed).",
                    page_title, page_url,
                )
                raise LinkedInAuthWallError(
                    f"LinkedIn auth wall detected (title={page_title!r}, url={page_url}). "
                    "Update LINKEDIN_LI_AT in backend/.env."
                )

            # ── Human behaviour ───────────────────────────────────────────────
            await _human_scroll(page, 300, 700)
            await _human_jitter(1_200, 2_500)

            # ── Selector scan ─────────────────────────────────────────────────
            for selector in _PLAYWRIGHT_JD_SELECTORS:
                try:
                    await page.wait_for_selector(selector, timeout=5_000)
                except Exception:
                    logger.debug(
                        "[linkedin_playwright] selector %r absent on %s",
                        selector, url,
                    )
                    continue

                node = await page.query_selector(selector)
                if not node:
                    continue

                raw  = await node.inner_text()
                text = _clean_linkedin_text(raw)

                if _is_loginwall(text):
                    raise LinkedInAuthWallError(
                        "LinkedIn Playwright: JD container is a login wall. "
                        "Cookie may be expired. Refresh LINKEDIN_LI_AT in backend/.env."
                    )
                if len(text) >= _LI_MIN_CHARS:
                    logger.info(
                        "[linkedin_playwright] ✓ Extracted %d chars via selector=%r from %s",
                        len(text), selector, url,
                    )
                    return text

                logger.debug(
                    "[linkedin_playwright] selector %r → %d chars (too short) on %s",
                    selector, len(text), url,
                )

            # ── Full body fallback ────────────────────────────────────────────
            body_text = _clean_linkedin_text(await page.inner_text("body"))
            if _is_loginwall(body_text):
                raise LinkedInAuthWallError(
                    "LinkedIn Playwright: full page is a login wall. "
                    "Refresh LINKEDIN_LI_AT in backend/.env. "
                    f"page_title={page_title!r}"
                )
            if len(body_text) >= _LI_MIN_CHARS:
                logger.warning(
                    "[linkedin_playwright] All selectors failed — body fallback (%d chars) for %s",
                    len(body_text), url,
                )
                return body_text

            raise ValueError(
                f"LinkedIn Playwright: no usable content on {url} after all selectors "
                f"and body fallback. page_title={page_title!r} body_len={len(body_text)}"
            )
        finally:
            await page.close()  # pages are closed; the context/session stays alive


def _linkedin_scrape(url: str) -> str:
    """
    LinkedIn JD scraper — unauthenticated requests + BeautifulSoup path.

    Used only when LINKEDIN_LI_AT is absent.  When li_at is set,
    scrape_jd_text_async() routes directly to _linkedin_scrape_async (async
    Playwright) which correctly handles LinkedIn's React SPA rendering.

    Extraction strategies (first to yield ≥ _LI_MIN_CHARS wins):
      1. JSON-LD <script type="application/ld+json"> description field
      2. .jobs-description-content__text container only — no fallbacks

    HTTP 403 / 999 → ValueError (LinkedIn hard block).
    No extractable content → ValueError (soft login wall or expired posting).
    """
    _linkedin_rate_wait()

    try:
        resp = requests.get(url, headers=_LINKEDIN_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response else 0
        if code in (403, 999):
            raise ValueError(
                f"LinkedIn blocked the scrape request (HTTP {code}). "
                "Set LINKEDIN_LI_AT in backend/.env for authenticated Playwright access."
            ) from exc
        raise

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Strategy 1: JSON-LD structured data ──────────────────────────────────
    # LinkedIn embeds <script type="application/ld+json"> with a "description"
    # field on public job pages — richest signal when available.
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            desc_html = ""
            if isinstance(data, dict):
                desc_html = data.get("description", "")
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("description"):
                        desc_html = item["description"]
                        break
            if desc_html:
                desc = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
                desc = _clean_linkedin_text(desc)
                if len(desc) >= _LI_MIN_CHARS and not _is_loginwall(desc):
                    logger.info(
                        "[linkedin_scraper] JSON-LD extraction: %d chars from %s",
                        len(desc), url,
                    )
                    return desc
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # ── Strategy 2: authoritative JD container only ──────────────────────────
    # Only the .jobs-description-content__text container is ingested.
    # No broader page content, no fallbacks.
    node = soup.find(class_="jobs-description-content__text")
    if node:
        text = _clean_linkedin_text(node.get_text(" ", strip=True))
        if len(text) >= _LI_MIN_CHARS and not _is_loginwall(text):
            logger.info(
                "[linkedin_scraper] .jobs-description-content__text: %d chars from %s",
                len(text), url,
            )
            return text

    raise ValueError(
        f"LinkedIn scraper: container '.jobs-description-content__text' not found "
        f"on {url}. The page is likely a login wall or the posting is expired/removed. "
        "Job marked FAILED."
    )


_JD_HANDLERS: list[tuple[str, Callable[[str], str]]] = [
    ("linkedin.com",        _linkedin_scrape),
    ("gotfriends.co.il",    lambda url: _lazy("gotfriends", url)),
    ("dialog.co.il",        lambda url: _lazy("dialog", url)),
    ("nisha.co.il",         lambda url: _lazy("nisha", url)),
    ("drushim.co.il",       lambda url: _lazy("drushim", url)),
    ("alljobs.co.il",       lambda url: _lazy("alljobs", url)),
]


def _lazy(source: str, url: str) -> str:
    """Lazily import and call the site-specific JD scraper."""
    if source == "gotfriends":
        from backend.scrapers.gotfriends_scraper import scrape_gotfriends_jd
        return scrape_gotfriends_jd(url)
    if source == "dialog":
        from backend.scrapers.dialog_scraper import scrape_dialog_jd
        return scrape_dialog_jd(url)
    if source == "nisha":
        from backend.scrapers.nisha_scraper import scrape_nisha_jd
        return scrape_nisha_jd(url)
    if source == "drushim":
        from backend.scrapers.drushim_scraper import scrape_drushim_jd
        return scrape_drushim_jd(url)
    if source == "alljobs":
        from backend.scrapers.alljobs_scraper import scrape_alljobs_jd
        return scrape_alljobs_jd(url)
    raise ValueError(f"Unknown source key: {source!r}")


# ── JD content gatekeeper ────────────────────────────────────────────────────
#
# Applied to every scraped text before it leaves this module.  A text that
# fails is NOT sent to the LLM — callers receive a ValueError so they can set
# the job to status='failed' and stop the pipeline immediately.
#
# Rules (all must pass):
#   1. Minimum length  — at least 300 characters of content.
#   2. At least one structural keyword from either of two groups must be present
#      (case-insensitive):
#        • Role-content keywords:  "responsibilities", "requirements",
#          "qualifications", "you will", "what you'll do", "about the role",
#          "about the job", "the role", "position overview", "job description"
#        • Company-content keywords: "description", "we are", "we're", "our team",
#          "join us", "about us"
#
# Rationale: LinkedIn login-wall pages, 404s, and sidebar-only scrapes all
# satisfy a length check but contain zero structural job-description language.
# This gate catches them before any LLM call is wasted.

_GATE_MIN_CHARS = 300

_GATE_ROLE_KEYWORDS: tuple[str, ...] = (
    "responsibilities", "requirements", "qualifications",
    "you will", "what you'll do", "what you will do",
    "about the role", "about the job", "about this role",
    "the role", "position overview", "job description",
    "key responsibilities", "role overview",
)
_GATE_COMPANY_KEYWORDS: tuple[str, ...] = (
    "description", "we are", "we're", "our team",
    "join us", "about us", "who we are",
)


def is_valid_job_content(text: str) -> bool:
    """
    Return True when *text* looks like genuine job-description content.

    Applies the two-part gatekeeper check: minimum length AND at least one
    structural keyword.  Callers should raise ``ValueError`` (which becomes
    status='failed') when this returns False, rather than proceeding to the LLM.
    """
    if len(text) < _GATE_MIN_CHARS:
        return False
    lower = text.lower()
    has_role    = any(kw in lower for kw in _GATE_ROLE_KEYWORDS)
    has_company = any(kw in lower for kw in _GATE_COMPANY_KEYWORDS)
    return has_role or has_company


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_jd_text(url: str) -> str:
    """
    Fetch and return the full JD text for a single job posting URL.

    Dispatches to the site-specific scraper for known domains; uses the
    generic html scraper for everything else.

    Raises
    ------
    ValueError
        When the page can't be fetched or contains no usable content.
    requests.HTTPError / requests.Timeout
        Propagated from underlying HTTP calls.
    """
    host = urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.")

    for domain, handler in _JD_HANDLERS:
        if host == domain or host.endswith("." + domain):
            logger.debug("[url_router] Routing %s → %s handler", url, domain)
            text = handler(url)
            if not is_valid_job_content(text):
                raise ValueError(
                    f"[url_router] Gatekeeper FAILED for {url} — text is {len(text)} chars "
                    "and contains no structural job-description keywords. "
                    "Likely a login wall, 404, or sidebar-only scrape. "
                    "Pipeline halted; job set to failed."
                )
            return text

    logger.debug("[url_router] No specific handler for %s — using generic scraper", host)
    text = _generic_scrape(url)
    if not is_valid_job_content(text):
        raise ValueError(
            f"[url_router] Gatekeeper FAILED for {url} — text is {len(text)} chars "
            "and contains no structural job-description keywords. "
            "Likely a login wall, 404, or sidebar-only scrape. "
            "Pipeline halted; job set to failed."
        )
    return text


async def scrape_jd_text_async(url: str) -> str:
    """
    Async entry point for JD fetching.  Call this from coroutines instead of
    ``await asyncio.to_thread(scrape_jd_text, url)``.

    Routing
    -------
    linkedin.com + LINKEDIN_LI_AT set
        → _linkedin_scrape_async  (persistent Playwright context, stealth + warm-up)
    linkedin.com + no LINKEDIN_LI_AT
        → asyncio.to_thread(_linkedin_scrape)  (unauthenticated requests)
    All other URLs
        → asyncio.to_thread(scrape_jd_text)  (existing sync scrapers)

    Raises
    ------
    LinkedInAuthWallError
        LinkedIn returned a login/authwall page.  The caller (hydrate_job) MUST
        route this to status='auth_wall' and MUST NOT increment enrichment_failures.
    ValueError
        Page loaded but no usable JD content found.
    requests.HTTPError / requests.Timeout
        Propagated from underlying HTTP calls.
    """
    from backend.config import LINKEDIN_LI_AT

    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    is_linkedin = host == "linkedin.com" or host.endswith(".linkedin.com")

    if is_linkedin:
        if LINKEDIN_LI_AT:
            logger.debug("[url_router_async] LinkedIn + li_at → persistent Playwright context")
            # LinkedInAuthWallError propagates unchanged — do NOT catch it here.
            text = await _linkedin_scrape_async(url, LINKEDIN_LI_AT)
        else:
            logger.debug("[url_router_async] LinkedIn, no li_at → requests (thread)")
            text = await asyncio.to_thread(_linkedin_scrape, url)

        if not is_valid_job_content(text):
            raise ValueError(
                f"[url_router_async] Gatekeeper FAILED for {url} — text is {len(text)} chars "
                "and contains no structural job-description keywords. "
                "Likely a LinkedIn login wall, expired posting, or bot-block. "
                "Pipeline halted; job set to failed."
            )
        return text

    # Non-LinkedIn: scrape_jd_text already applies the gate.
    logger.debug("[url_router_async] Non-LinkedIn → sync scraper (thread): %s", host)
    return await asyncio.to_thread(scrape_jd_text, url)


def get_scraper_for_url(url: str) -> Optional[BaseScraper]:
    """
    Return a configured BaseScraper instance for the given source URL,
    or None if no specific scraper is registered for that host.

    The returned scraper is a fresh instance with default settings.
    For richer control (keyword filters, user_id) construct the scraper
    directly instead.
    """
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")

    if "gotfriends.co.il" in host:
        from backend.scrapers.gotfriends_scraper import GotfriendsScraper
        return GotfriendsScraper(company_url=url)

    if "dialog.co.il" in host:
        from backend.scrapers.dialog_scraper import DialogScraper
        return DialogScraper(company_url=url)

    if "nisha.co.il" in host:
        from backend.scrapers.nisha_scraper import NishaScraper
        return NishaScraper(company_url=url)

    if "drushim.co.il" in host:
        from backend.scrapers.drushim_scraper import DrushimScraper
        return DrushimScraper(company_url=url)

    if "alljobs.co.il" in host:
        from backend.scrapers.alljobs_scraper import AllJobsScraper
        return AllJobsScraper(company_url=url)

    if "comeet.co" in host or "comeet.com" in host:
        from backend.scrapers.comeet_adapter import ComeetAdapter
        return ComeetAdapter(company_name="Comeet", company_url=url)

    # LinkedIn is search-based (query + location), not URL-routed.
    # Use LinkedInScraper directly with explicit query/location params instead.

    logger.debug("[url_router] No registered scraper for host '%s'", host)
    return None
