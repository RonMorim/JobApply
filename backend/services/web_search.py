"""
Web Search Service — DuckDuckGo HTML wrapper.

No API key required. Uses httpx + BeautifulSoup4, both already in requirements.
Rate-limited to 1.5 s between requests to be respectful to DDG servers.

Public API
----------
search(query, max_results=5) -> list[SearchResult]   (async)
"""
from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_DDG_URL        = "https://html.duckduckgo.com/html/"
_MIN_INTERVAL_S = 1.5          # polite rate-limit between requests
_REQUEST_TIMEOUT = 10.0        # seconds
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type":    "application/x-www-form-urlencoded",
}

_last_request_at: float = 0.0


@dataclass
class SearchResult:
    title:   str
    snippet: str
    url:     str


async def search(query: str, max_results: int = 5) -> list[SearchResult]:
    """
    Search DuckDuckGo and return up to max_results results.

    Returns an empty list on any network or parse failure — never raises.
    Rate-limits itself to _MIN_INTERVAL_S between calls.
    """
    global _last_request_at

    # Enforce minimum interval between requests
    elapsed = time.monotonic() - _last_request_at
    if elapsed < _MIN_INTERVAL_S:
        await asyncio.sleep(_MIN_INTERVAL_S - elapsed)
    _last_request_at = time.monotonic()

    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.post(
                _DDG_URL,
                data={"q": query, "kl": "us-en", "ia": "web"},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("[web_search] DDG request failed for %r: %s", query, exc)
        return []

    return _parse_results(resp.text, max_results)


def _parse_results(html: str, max_results: int) -> list[SearchResult]:
    soup    = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    for div in soup.select(".result")[:max_results * 2]:  # oversample, filter below
        title_a    = div.select_one(".result__title a")
        snippet_el = div.select_one(".result__snippet")

        if not title_a:
            continue

        title   = title_a.get_text(strip=True)
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        raw_href = title_a.get("href", "")
        url     = _extract_url(raw_href)

        if not title and not snippet:
            continue

        results.append(SearchResult(title=title, snippet=snippet, url=url))
        if len(results) >= max_results:
            break

    return results


def _extract_url(href: str) -> str:
    """
    DDG redirects have the form //duckduckgo.com/l/?uddg=<encoded-url>&...
    Extract the real destination URL from the uddg param, or return href as-is.
    """
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        qs     = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return urllib.parse.unquote(qs["uddg"][0])
    except Exception:
        pass
    return href
