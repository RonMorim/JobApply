"""
Centralized Anthropic client wrapper.

This module is the single place a call site should get an Anthropic client
from. It does not change any prompt, model, or business logic — it only
owns: client construction, timeout, retry-on-transient-failure, safe error
wrapping, and metadata-only logging (never prompt/response content).

Streaming calls (chat.py) are covered by stream_llm() — a thin factory that
returns the same Anthropic streaming context manager, built from the shared
client, without wrapping stream errors (see its docstring for why).

Not yet covered (by design):
  - A second LLM provider — the signature below deliberately avoids leaking
    anthropic-specific types into its parameters so another provider could
    implement the same call_llm() shape later, but no abstraction layer is
    built yet.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from backend.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

# ── Shared client ──────────────────────────────────────────────────────────────
# One client for the whole process, built from the centrally-validated
# ANTHROPIC_API_KEY (backend/config.py) instead of each call site reading
# os.getenv("ANTHROPIC_API_KEY") itself.
#
# max_retries=0: the SDK has its own built-in retry, but retry is handled
# explicitly in call_llm() below instead, so the policy is visible in one
# place, doesn't silently compound with the SDK's own retry, and is easy to
# unit test by mocking messages.create() directly.
_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=0)

_DEFAULT_TIMEOUT_S = 60.0
_DEFAULT_MAX_RETRIES = 2
_RETRY_BASE_DELAY_S = 1.0

# Transient/infrastructure failures — safe to retry:
#   RateLimitError      — HTTP 429
#   APIConnectionError   — network failure (APITimeoutError is a subclass of
#                          this, so request timeouts are covered too)
#   InternalServerError  — HTTP 5xx
# Deliberately NOT included: BadRequestError (400), AuthenticationError (401),
# PermissionDeniedError (403), NotFoundError (404), ConflictError (409),
# UnprocessableEntityError (422) — these are client/request errors that will
# not resolve themselves on retry.
_RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


class LLMCallError(RuntimeError):
    """
    Safe, generic error raised for any LLM call failure (after retries are
    exhausted for transient errors, or immediately for non-retryable ones).

    The message is always a short, generic, user-safe string — never the
    raw provider exception text, which can echo back request/response
    internals. The real exception is logged server-side (by type and status
    code only, not by message body) before this is raised; use `from exc`
    at the raise site if you need the original traceback for debugging.
    """


@dataclass
class LLMResult:
    text: str                      # convenience: response.content[0].text
    model: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    latency_ms: float
    attempts: int
    raw: Any                       # full anthropic.types.Message


async def call_llm(
    *,
    system: Optional[str] = None,
    messages: list[dict],
    model: str,
    max_tokens: int,
    purpose: str,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: Optional[list] = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> LLMResult:
    """
    Make one non-streaming Anthropic call with timeout, transient-failure
    retry, and safe metadata-only logging.

    `purpose` / `user_id` / `job_id` are for server-side log correlation
    ONLY. They are never sent to Anthropic and never appear in `system` or
    `messages` — callers must not fold them into the prompt themselves
    expecting this function to do it; it doesn't.

    `tools` is passed straight through to messages.create() unchanged (e.g.
    Anthropic server-side tools like web_search) — callers driving a
    multi-turn tool/pause_turn loop should call call_llm() once per turn and
    inspect `.raw.stop_reason` / `.raw.content` themselves; this function
    always makes exactly one call per invocation.

    Never logs: system, messages, prompt content, or any field of the
    response other than token counts. Raises LLMCallError on failure —
    never re-raises the raw anthropic exception to the caller.
    """
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system is not None:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    if tools is not None:
        kwargs["tools"] = tools

    attempt = 0
    start = time.monotonic()

    while True:
        attempt += 1
        try:
            response = await _client.messages.create(timeout=timeout, **kwargs)
            break
        except _RETRYABLE_EXCEPTIONS as exc:
            status_code = getattr(exc, "status_code", None)
            if attempt > max_retries:
                logger.error(
                    "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
                    "FAILED after %d attempt(s): %s (status=%s)",
                    purpose, model, user_id, job_id, attempt, type(exc).__name__, status_code,
                )
                raise LLMCallError(
                    "The AI service is temporarily unavailable. Please try again shortly."
                ) from exc
            logger.warning(
                "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
                "attempt=%d/%d retrying after %s (status=%s)",
                purpose, model, user_id, job_id, attempt, max_retries + 1,
                type(exc).__name__, status_code,
            )
            await asyncio.sleep(_RETRY_BASE_DELAY_S * attempt)
        except anthropic.APIError as exc:
            # Non-retryable: bad request, auth, permission, not found,
            # conflict, unprocessable entity, or any other API error.
            logger.error(
                "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
                "NON-RETRYABLE %s (status=%s)",
                purpose, model, user_id, job_id, type(exc).__name__,
                getattr(exc, "status_code", None),
            )
            raise LLMCallError(
                "The AI request could not be completed. Please try again or contact support."
            ) from exc
        except Exception as exc:
            # Anything else unexpected — still safe-wrap, never leak str(exc).
            logger.exception(
                "[llm_client] purpose=%s model=%s user_id=%s job_id=%s UNEXPECTED %s",
                purpose, model, user_id, job_id, type(exc).__name__,
            )
            raise LLMCallError(
                "An unexpected error occurred while contacting the AI service."
            ) from exc

    latency_ms = (time.monotonic() - start) * 1000

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
    output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None

    logger.info(
        "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
        "input_tokens=%s output_tokens=%s latency_ms=%.0f attempts=%d",
        purpose, model, user_id, job_id, input_tokens, output_tokens, latency_ms, attempt,
    )

    text = ""
    if response.content:
        text = getattr(response.content[0], "text", "") or ""

    return LLMResult(
        text=text,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        attempts=attempt,
        raw=response,
    )


def stream_llm(
    *,
    system: Optional[str] = None,
    messages: list[dict],
    model: str,
    max_tokens: int,
    purpose: str,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    temperature: Optional[float] = None,
    tools: Optional[list] = None,
    tool_choice: Optional[dict] = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
):
    """
    Return the Anthropic streaming context manager for one turn, built from
    the shared centralized client.

    This is a thin factory, not a wrapping context manager: it does not
    catch or translate stream errors itself, because a streaming failure can
    happen mid-stream after bytes have already been sent to the client. The
    caller keeps its own `async with stream_llm(...) as stream: async for
    event in stream:` loop and its own try/except around it, exactly as it
    does today with a raw `client.messages.stream(...)` call.

    kwargs are assembled the same optional-only way as call_llm(): system /
    temperature / tools / tool_choice are only added to the request if not
    None, so omitting them behaves exactly like the direct SDK call did.

    Never logs system, messages, tools, or response content — only a single
    metadata-only "stream start" line (purpose/model/user_id/job_id).
    """
    kwargs: dict = dict(model=model, max_tokens=max_tokens, messages=messages)
    if system is not None:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    if tools is not None:
        kwargs["tools"] = tools
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice

    logger.info(
        "[llm_client] STREAM START purpose=%s model=%s user_id=%s job_id=%s",
        purpose, model, user_id, job_id,
    )

    return _client.messages.stream(timeout=timeout, **kwargs)
