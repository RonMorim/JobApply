"""
Tests for backend.services.llm_client — the centralized Anthropic wrapper.

No real network calls: backend.services.llm_client._client.messages.create is
patched with an AsyncMock in every test.
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
import pytest

from unittest.mock import MagicMock

from backend.services.llm_client import LLMCallError, call_llm, stream_llm
import backend.services.llm_client as llm_client_module


# ── Fake exception / response builders ────────────────────────────────────────

def _fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _fake_http_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_fake_request())


def _rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError("rate limited", response=_fake_http_response(429), body=None)


def _internal_server_error() -> anthropic.InternalServerError:
    return anthropic.InternalServerError("server error", response=_fake_http_response(500), body=None)


def _bad_request_error() -> anthropic.BadRequestError:
    return anthropic.BadRequestError("bad request", response=_fake_http_response(400), body=None)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_fake_request())


def _fake_message(text: str = "hello from claude", input_tokens: int = 10, output_tokens: int = 5):
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


_CALL_KWARGS = dict(
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "hi"}],
    model="claude-haiku-4-5",
    max_tokens=100,
    purpose="test_call",
    user_id="user-123",
    job_id="job-456",
)


# ── Success path ───────────────────────────────────────────────────────────────

def test_success_path_returns_text_and_usage():
    fake_response = _fake_message(text="the answer")

    async def run():
        with patch.object(
            llm_client_module._client.messages, "create", new=AsyncMock(return_value=fake_response)
        ) as mock_create:
            result = await call_llm(**_CALL_KWARGS)
            assert result.text == "the answer"
            assert result.input_tokens == 10
            assert result.output_tokens == 5
            assert result.attempts == 1
            assert mock_create.call_count == 1

    asyncio.run(run())


def test_system_omitted_when_not_provided():
    """Some call sites (e.g. resume.py's vision helpers) never had a system
    prompt at all — call_llm must not force an empty one onto the request."""
    fake_response = _fake_message()
    kwargs_without_system = {k: v for k, v in _CALL_KWARGS.items() if k != "system"}

    async def run():
        with patch.object(
            llm_client_module._client.messages, "create", new=AsyncMock(return_value=fake_response)
        ) as mock_create:
            await call_llm(**kwargs_without_system)
            assert "system" not in mock_create.call_args.kwargs

    asyncio.run(run())


def test_tools_param_passed_through_when_provided():
    fake_response = _fake_message()
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 4}]

    async def run():
        with patch.object(
            llm_client_module._client.messages, "create", new=AsyncMock(return_value=fake_response)
        ) as mock_create:
            await call_llm(**_CALL_KWARGS, tools=tools)
            assert mock_create.call_args.kwargs.get("tools") == tools

    asyncio.run(run())


def test_tools_param_omitted_when_not_provided():
    fake_response = _fake_message()

    async def run():
        with patch.object(
            llm_client_module._client.messages, "create", new=AsyncMock(return_value=fake_response)
        ) as mock_create:
            await call_llm(**_CALL_KWARGS)
            assert "tools" not in mock_create.call_args.kwargs

    asyncio.run(run())


# ── Retry path ─────────────────────────────────────────────────────────────────

def test_retries_then_succeeds_on_transient_failure():
    fake_response = _fake_message(text="succeeded after retries")
    mock_create = AsyncMock(side_effect=[_rate_limit_error(), _internal_server_error(), fake_response])

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with patch.object(llm_client_module, "_RETRY_BASE_DELAY_S", 0.001):
                result = await call_llm(**_CALL_KWARGS, max_retries=2)
                assert result.text == "succeeded after retries"
                assert result.attempts == 3
                assert mock_create.call_count == 3

    asyncio.run(run())


def test_retry_exhausted_raises_llm_call_error():
    mock_create = AsyncMock(side_effect=[_rate_limit_error(), _rate_limit_error()])

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with patch.object(llm_client_module, "_RETRY_BASE_DELAY_S", 0.001):
                with pytest.raises(LLMCallError):
                    await call_llm(**_CALL_KWARGS, max_retries=1)
                # max_retries=1 → 2 total attempts (1 initial + 1 retry), then raise
                assert mock_create.call_count == 2

    asyncio.run(run())


# ── Non-retryable errors ────────────────────────────────────────────────────────

def test_non_retryable_error_raises_immediately_without_retry():
    mock_create = AsyncMock(side_effect=_bad_request_error())

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with pytest.raises(LLMCallError):
                await call_llm(**_CALL_KWARGS, max_retries=3)
            # A 4xx error must NOT be retried, regardless of max_retries.
            assert mock_create.call_count == 1

    asyncio.run(run())


def test_connection_error_is_retried():
    fake_response = _fake_message()
    mock_create = AsyncMock(side_effect=[_connection_error(), fake_response])

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with patch.object(llm_client_module, "_RETRY_BASE_DELAY_S", 0.001):
                result = await call_llm(**_CALL_KWARGS, max_retries=1)
                assert result.attempts == 2
                assert mock_create.call_count == 2

    asyncio.run(run())


# ── Safe error wrapping ──────────────────────────────────────────────────────────

def test_llm_call_error_message_never_contains_raw_exception_text():
    secret_marker = "RAW_PROVIDER_INTERNAL_DETAIL_12345"
    mock_create = AsyncMock(side_effect=anthropic.BadRequestError(secret_marker, response=_fake_http_response(400), body=None))

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with pytest.raises(LLMCallError) as exc_info:
                await call_llm(**_CALL_KWARGS)
            assert secret_marker not in str(exc_info.value)

    asyncio.run(run())


# ── Safe logging ──────────────────────────────────────────────────────────────

def test_logging_never_includes_prompt_or_response_content(caplog):
    secret_system = "SECRET_SYSTEM_PROMPT_MARKER"
    secret_user_message = "SECRET_USER_MESSAGE_MARKER"
    secret_response_text = "SECRET_RESPONSE_TEXT_MARKER"

    fake_response = _fake_message(text=secret_response_text)

    async def run():
        with patch.object(
            llm_client_module._client.messages, "create", new=AsyncMock(return_value=fake_response)
        ):
            with caplog.at_level(logging.DEBUG, logger="backend.services.llm_client"):
                await call_llm(
                    system=secret_system,
                    messages=[{"role": "user", "content": secret_user_message}],
                    model="claude-haiku-4-5",
                    max_tokens=100,
                    purpose="test_no_leak",
                    user_id="user-123",
                    job_id="job-456",
                )

    asyncio.run(run())

    all_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_system not in all_log_text
    assert secret_user_message not in all_log_text
    assert secret_response_text not in all_log_text
    # Sanity check: logging DID actually happen (the assertions above aren't
    # vacuously true because nothing was logged at all).
    assert any("llm_client" in record.getMessage() for record in caplog.records)


def test_logging_on_retry_never_includes_prompt_or_error_body(caplog):
    secret_system = "SECRET_SYSTEM_PROMPT_MARKER_2"
    secret_error_body = "RAW_ERROR_BODY_SECRET_MARKER"
    fake_response = _fake_message()

    mock_create = AsyncMock(
        side_effect=[
            anthropic.RateLimitError(secret_error_body, response=_fake_http_response(429), body=None),
            fake_response,
        ]
    )

    async def run():
        with patch.object(llm_client_module._client.messages, "create", new=mock_create):
            with patch.object(llm_client_module, "_RETRY_BASE_DELAY_S", 0.001):
                with caplog.at_level(logging.DEBUG, logger="backend.services.llm_client"):
                    await call_llm(
                        system=secret_system,
                        messages=[{"role": "user", "content": "hi"}],
                        model="claude-haiku-4-5",
                        max_tokens=100,
                        purpose="test_retry_no_leak",
                        max_retries=1,
                    )

    asyncio.run(run())

    all_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_system not in all_log_text
    assert secret_error_body not in all_log_text


# ── stream_llm() — Phase 4f streaming factory ──────────────────────────────────
#
# stream_llm() is a thin factory: it does not call/await anything itself, it
# just assembles kwargs and returns whatever _client.messages.stream(...)
# returns. So these tests patch _client.messages.stream with a plain
# MagicMock (not AsyncMock — messages.stream() is a regular sync method that
# returns an async context manager, it is not itself a coroutine) and assert
# on the kwargs it was called with.

_STREAM_KWARGS = dict(
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "hi"}],
    model="claude-sonnet-4-6",
    max_tokens=1024,
    purpose="test_stream",
    user_id="user-123",
    job_id="job-456",
)


def test_stream_llm_returns_client_stream_manager_with_assembled_kwargs():
    sentinel = MagicMock(name="stream_manager")
    with patch.object(llm_client_module._client.messages, "stream", new=MagicMock(return_value=sentinel)) as mock_stream:
        result = stream_llm(**_STREAM_KWARGS)
        assert result is sentinel
        assert mock_stream.call_args.kwargs["model"] == "claude-sonnet-4-6"
        assert mock_stream.call_args.kwargs["max_tokens"] == 1024
        assert mock_stream.call_args.kwargs["system"] == _STREAM_KWARGS["system"]
        assert mock_stream.call_args.kwargs["messages"] == _STREAM_KWARGS["messages"]


def test_stream_llm_system_omitted_when_not_provided():
    kwargs_without_system = {k: v for k, v in _STREAM_KWARGS.items() if k != "system"}
    with patch.object(llm_client_module._client.messages, "stream", new=MagicMock(return_value=MagicMock())) as mock_stream:
        stream_llm(**kwargs_without_system)
        assert "system" not in mock_stream.call_args.kwargs


def test_stream_llm_tools_and_tool_choice_passed_through_when_provided():
    tools = [{"name": "tailor_resume_for_job", "input_schema": {"type": "object"}}]
    tool_choice = {"type": "none"}
    with patch.object(llm_client_module._client.messages, "stream", new=MagicMock(return_value=MagicMock())) as mock_stream:
        stream_llm(**_STREAM_KWARGS, tools=tools, tool_choice=tool_choice)
        assert mock_stream.call_args.kwargs.get("tools") == tools
        assert mock_stream.call_args.kwargs.get("tool_choice") == tool_choice


def test_stream_llm_tools_and_tool_choice_omitted_when_not_provided():
    with patch.object(llm_client_module._client.messages, "stream", new=MagicMock(return_value=MagicMock())) as mock_stream:
        stream_llm(**_STREAM_KWARGS)
        assert "tools" not in mock_stream.call_args.kwargs
        assert "tool_choice" not in mock_stream.call_args.kwargs


def test_stream_llm_logging_never_includes_prompt_or_tool_content(caplog):
    secret_system = "SECRET_STREAM_SYSTEM_MARKER"
    secret_user_message = "SECRET_STREAM_USER_MARKER"
    secret_tool_content = "SECRET_STREAM_TOOL_MARKER"
    tools = [{"name": secret_tool_content, "input_schema": {"type": "object"}}]

    with patch.object(llm_client_module._client.messages, "stream", new=MagicMock(return_value=MagicMock())):
        with caplog.at_level(logging.DEBUG, logger="backend.services.llm_client"):
            stream_llm(
                system=secret_system,
                messages=[{"role": "user", "content": secret_user_message}],
                model="claude-sonnet-4-6",
                max_tokens=1024,
                purpose="test_stream_no_leak",
                tools=tools,
            )

    all_log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_system not in all_log_text
    assert secret_user_message not in all_log_text
    assert secret_tool_content not in all_log_text
    assert any("STREAM START" in record.getMessage() for record in caplog.records)
