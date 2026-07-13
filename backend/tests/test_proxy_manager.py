import pytest
import httpx
from unittest.mock import AsyncMock, patch
from backend.scrapers.proxy_manager import ProxyManager
import os

@pytest.fixture
def mock_env():
    with patch.dict(os.environ, {"PROXY_LIST": "http://proxy1:8080,http://proxy2:8080"}, clear=True):
        yield

@pytest.mark.asyncio
async def test_proxy_rotation(mock_env):
    manager = ProxyManager()
    assert manager.get_proxy() == "http://proxy1:8080"
    assert manager.get_proxy() == "http://proxy2:8080"
    assert manager.get_proxy() == "http://proxy1:8080"

@pytest.mark.asyncio
async def test_fetch_with_retry_success(mock_env):
    manager = ProxyManager()
    
    mock_response = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
    
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_response
        
        resp = await manager.fetch_with_retry("http://test.com")
        
        assert resp.status_code == 200
        mock_request.assert_called_once()
        
        # Verify proxy was used (proxy1)
        assert manager._current_index == 1

@pytest.mark.asyncio
async def test_fetch_with_retry_429(mock_env):
    manager = ProxyManager()
    
    mock_429 = httpx.Response(429, request=httpx.Request("GET", "http://test.com"))
    mock_200 = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
    
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = [
            httpx.HTTPStatusError("429 Too Many Requests", request=mock_429.request, response=mock_429),
            mock_200
        ]
        
        # Base backoff 0.01 to speed up test
        resp = await manager.fetch_with_retry("http://test.com", base_backoff=0.01)
        
        assert resp.status_code == 200
        assert mock_request.call_count == 2
        # After two attempts, proxy index should be 0 (proxy1 -> proxy2 -> back to proxy1)
        assert manager._current_index == 0

@pytest.mark.asyncio
async def test_fallback_no_proxy():
    with patch.dict(os.environ, {}, clear=True):
        manager = ProxyManager()
        assert manager.get_proxy() is None

        mock_response = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            resp = await manager.fetch_with_retry("http://test.com")
            assert resp.status_code == 200


@pytest.mark.asyncio
async def test_retry_preserves_http_method(mock_env):
    # Regression: method was popped inside the retry loop, so a retried POST
    # silently degraded to GET on attempt 2+.
    manager = ProxyManager(min_host_interval=0)

    mock_500 = httpx.Response(500, request=httpx.Request("POST", "http://test.com"))
    mock_200 = httpx.Response(200, request=httpx.Request("POST", "http://test.com"))

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = [
            httpx.HTTPStatusError("500", request=mock_500.request, response=mock_500),
            mock_200,
        ]
        resp = await manager.fetch_with_retry("http://test.com", base_backoff=0.01, method="POST")
        assert resp.status_code == 200
        assert mock_request.call_count == 2
        for call in mock_request.call_args_list:
            assert call.kwargs["method"] == "POST"


@pytest.mark.asyncio
async def test_default_browser_user_agent_and_override(mock_env):
    manager = ProxyManager(min_host_interval=0)
    mock_response = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_response
        await manager.fetch_with_retry("http://test.com")
        ua = mock_request.call_args.kwargs["headers"]["User-Agent"]
        assert "Mozilla/5.0" in ua          # browser UA, not python-httpx default

        await manager.fetch_with_retry("http://test.com", headers={"User-Agent": "custom-ua"})
        assert mock_request.call_args.kwargs["headers"]["User-Agent"] == "custom-ua"


@pytest.mark.asyncio
async def test_unrecoverable_status_does_not_retry(mock_env):
    manager = ProxyManager(min_host_interval=0)
    mock_404 = httpx.Response(404, request=httpx.Request("GET", "http://test.com"))

    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.side_effect = httpx.HTTPStatusError(
            "404", request=mock_404.request, response=mock_404,
        )
        with pytest.raises(httpx.HTTPStatusError):
            await manager.fetch_with_retry("http://test.com", base_backoff=0.01)
        assert mock_request.call_count == 1   # hard failure — no rotation, no retry


@pytest.mark.asyncio
async def test_per_host_politeness_interval():
    import time as _time
    with patch.dict(os.environ, {}, clear=True):
        manager = ProxyManager(min_host_interval=0.2)
        mock_response = httpx.Response(200, request=httpx.Request("GET", "http://test.com"))

        with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response
            start = _time.monotonic()
            await manager.fetch_with_retry("http://test.com/a")
            await manager.fetch_with_retry("http://test.com/b")   # same host — throttled
            elapsed = _time.monotonic() - start
            assert elapsed >= 0.2

            # Different host — no shared throttle slot
            start = _time.monotonic()
            await manager.fetch_with_retry("http://other.com/a")
            assert _time.monotonic() - start < 0.15
