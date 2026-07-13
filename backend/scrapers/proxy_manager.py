import os
import random
import logging
import asyncio
import time
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Browser User-Agent sent by default — httpx's own "python-httpx/x.y" UA is an
# instant block signal for most job boards. Callers may override via headers=.
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


class ProxyManager:
    """
    Manages a pool of HTTP proxies and provides a robust fetch method
    that handles rotation, rate limits (429), and exponential backoff.

    Politeness: requests to the same host are spaced at least
    `min_host_interval` seconds apart (conservative default 0.5s), so a burst
    of scrapes against one board can't trip IP-level rate limits. Per-source
    scrapers that need a different cadence pass their own value.
    """

    def __init__(
        self,
        proxy_list_env: str = "PROXY_LIST",
        min_host_interval: float = 0.5,
    ) -> None:
        self._proxies: List[str] = self._load_proxies(proxy_list_env)
        self._current_index: int = 0
        self._min_host_interval = max(0.0, min_host_interval)
        self._host_next_slot: Dict[str, float] = {}
        self._throttle_lock = asyncio.Lock()
        if self._proxies:
            logger.info("[ProxyManager] Loaded %d proxies from environment.", len(self._proxies))
        else:
            logger.warning("[ProxyManager] No proxies configured. Falling back to direct requests.")

    async def _respect_host_interval(self, url: str) -> None:
        """Reserve the next request slot for this host; sleep until it opens."""
        if self._min_host_interval <= 0:
            return
        host = (urlparse(url).hostname or "").lower()
        async with self._throttle_lock:
            now  = time.monotonic()
            slot = max(self._host_next_slot.get(host, now), now)
            self._host_next_slot[host] = slot + self._min_host_interval
        wait = slot - now
        if wait > 0:
            await asyncio.sleep(wait)

    def _load_proxies(self, env_var: str) -> List[str]:
        raw_list = os.environ.get(env_var, "")
        proxies = [p.strip() for p in raw_list.split(",") if p.strip()]
        return proxies

    def get_proxy(self) -> Optional[str]:
        """Return the next proxy in a round-robin fashion, or None if no proxies."""
        if not self._proxies:
            return None
        
        proxy = self._proxies[self._current_index]
        self._current_index = (self._current_index + 1) % len(self._proxies)
        return proxy

    async def fetch_with_retry(
        self, 
        url: str, 
        max_retries: int = 3, 
        base_backoff: float = 2.0, 
        client_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Fetch a URL using httpx, automatically rotating proxies on failure
        and applying exponential backoff for 429s or connection errors.
        """
        client_kwargs = client_kwargs or {}
        # Ensure a reasonable timeout if not provided
        if "timeout" not in client_kwargs:
            client_kwargs["timeout"] = 15.0

        # Resolve method/headers ONCE, outside the retry loop — popping inside
        # the loop consumed the method on attempt 1 and silently degraded every
        # retried POST/PUT to a GET.
        method  = kwargs.pop("method", "GET")
        headers = {**DEFAULT_HEADERS, **(kwargs.pop("headers", None) or {})}

        last_exception = None
        retry_after: Optional[float] = None

        for attempt in range(max_retries):
            await self._respect_host_interval(url)
            proxy = self.get_proxy()

            # Setup client proxy arguments
            if proxy:
                # httpx >= 0.20.0 uses 'proxy' parameter
                client_kwargs["proxy"] = proxy

            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        **kwargs
                    )

                    if response.status_code == 429:
                        logger.warning(
                            "[ProxyManager] 429 Rate Limit on %s (attempt %d). Rotating...",
                            url, attempt + 1
                        )
                        response.raise_for_status()

                    response.raise_for_status()
                    return response

            except httpx.HTTPStatusError as e:
                last_exception = e
                # Only retry on 429, 500, 502, 503, 504
                if e.response.status_code not in (429, 500, 502, 503, 504):
                    logger.error("[ProxyManager] Unrecoverable HTTP error %d on %s", e.response.status_code, url)
                    raise
                # Honour Retry-After on 429s when the server provides one
                retry_after = None
                if e.response.status_code == 429:
                    raw = e.response.headers.get("Retry-After", "")
                    try:
                        retry_after = min(float(raw), 60.0) if raw else None
                    except ValueError:
                        retry_after = None
            except httpx.RequestError as e:
                last_exception = e
                retry_after = None
                logger.warning(
                    "[ProxyManager] RequestError on %s using proxy %s: %s",
                    url, proxy or "DIRECT", str(e)
                )

            # Backoff before retry
            if attempt < max_retries - 1:
                sleep_time = base_backoff * (2 ** attempt) + random.uniform(0, 1)
                if retry_after is not None:
                    sleep_time = max(sleep_time, retry_after)
                logger.debug("[ProxyManager] Sleeping %.2fs before retry...", sleep_time)
                await asyncio.sleep(sleep_time)

        logger.error("[ProxyManager] Max retries (%d) reached for %s", max_retries, url)
        if last_exception:
            raise last_exception
        
        raise Exception(f"Failed to fetch {url}")
