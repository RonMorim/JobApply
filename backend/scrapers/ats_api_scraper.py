"""
ATS structured-API scrapers — Greenhouse and Lever.

Both platforms expose public, unauthenticated JSON APIs that mirror the
content of their hosted job pages. Calling these APIs directly is more
reliable than generic HTML scraping: no reliance on og:title/og:site_name
meta tags, no risk of picking up nav/sidebar noise, and immune to any future
frontend markup changes on either platform.

Each function returns a plain dict with keys {title, company, raw_text} on
success, or None when the URL doesn't match the platform's known path shape
or the API call fails for any reason — callers fall back to the generic
scraper in that case.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import urlparse

import requests

from backend.scrapers.parsing_engine import ParsingEngine

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 10


def _humanize_slug(slug: str) -> str:
    return re.sub(r"[-_]", " ", slug).strip().title() or "Unknown"


def _html_to_text(raw_html: str) -> str:
    """
    Convert an HTML fragment to plain text.

    Delegates to the shared ParsingEngine (Core Scraping Architecture) —
    it handles the entity-encoded markup Greenhouse/Lever payloads sometimes
    ship (e.g. `&lt;div&gt;` instead of `<div>`).
    """
    return ParsingEngine.html_to_text(raw_html)


# ── Greenhouse ────────────────────────────────────────────────────────────────

# Matches both legacy boards.greenhouse.io and the newer job-boards.greenhouse.io
# domains, path shape: /{board_token}/jobs/{job_id}
_GREENHOUSE_PATH_RE = re.compile(r"^/([^/]+)/jobs/(\d+)")


def try_greenhouse_api(url: str) -> Optional[dict]:
    """Fetch a Greenhouse job posting via the public boards-api. None on any failure."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host not in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        return None

    match = _GREENHOUSE_PATH_RE.match(urlparse(url).path)
    if not match:
        logger.debug("[ats_api_scraper] Greenhouse URL path unrecognized: %s", url)
        return None

    board_token, job_id = match.group(1), match.group(2)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"

    try:
        resp = requests.get(api_url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[ats_api_scraper] Greenhouse API failed for %s: %r", url, exc)
        return None

    title = (data.get("title") or "").strip()
    raw_text = _html_to_text(data.get("content") or "")
    if not title or len(raw_text) < 50:
        logger.debug("[ats_api_scraper] Greenhouse API returned thin content for %s", url)
        return None

    company = (data.get("company_name") or "").strip() or _humanize_slug(board_token)
    location = ((data.get("location") or {}).get("name") or "").strip()
    if location:
        raw_text = f"Location: {location}\n\n{raw_text}"

    logger.info("[ats_api_scraper] Greenhouse ✓ board=%s job_id=%s chars=%d", board_token, job_id, len(raw_text))
    return {"title": title, "company": company, "raw_text": raw_text}


# ── Lever ─────────────────────────────────────────────────────────────────────

# Path shape: /{company}/{posting_id}[/apply]
_LEVER_PATH_RE = re.compile(
    r"^/([^/]+)/([0-9a-fA-F-]{8,})"
)


def try_lever_api(url: str) -> Optional[dict]:
    """Fetch a Lever job posting via the public postings API. None on any failure."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host != "jobs.lever.co":
        return None

    match = _LEVER_PATH_RE.match(urlparse(url).path)
    if not match:
        logger.debug("[ats_api_scraper] Lever URL path unrecognized: %s", url)
        return None

    company_slug, posting_id = match.group(1), match.group(2)
    api_url = f"https://api.lever.co/v0/postings/{company_slug}/{posting_id}?mode=json"

    try:
        resp = requests.get(api_url, headers={"User-Agent": _UA}, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[ats_api_scraper] Lever API failed for %s: %r", url, exc)
        return None

    title = (data.get("text") or "").strip()
    if not title:
        logger.debug("[ats_api_scraper] Lever API returned no title for %s", url)
        return None

    sections: list[str] = []
    description = _html_to_text(data.get("description") or data.get("descriptionPlain") or "")
    if description:
        sections.append(description)

    for section in data.get("lists") or []:
        heading = (section.get("text") or "").strip()
        body = _html_to_text(section.get("content") or section.get("contentPlain") or "")
        if body:
            sections.append(f"{heading}\n{body}" if heading else body)

    additional = _html_to_text(data.get("additional") or data.get("additionalPlain") or "")
    if additional:
        sections.append(additional)

    raw_text = "\n\n".join(sections).strip()
    if len(raw_text) < 50:
        logger.debug("[ats_api_scraper] Lever API returned thin content for %s", url)
        return None

    categories = data.get("categories") or {}
    location = (categories.get("location") or "").strip()
    if location:
        raw_text = f"Location: {location}\n\n{raw_text}"

    company = _humanize_slug(company_slug)
    logger.info("[ats_api_scraper] Lever ✓ company=%s posting_id=%s chars=%d", company_slug, posting_id, len(raw_text))
    return {"title": title, "company": company, "raw_text": raw_text}
