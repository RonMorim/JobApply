"""
Centralized Anthropic client wrapper, with an automatic Gemini fallback.

This module is the single place a call site should get an Anthropic client
from. It does not change any prompt, model, or business logic — it only
owns: client construction, timeout, retry-on-transient-failure, safe error
wrapping, and metadata-only logging (never prompt/response content).

Fallback provider — both call_llm() and stream_llm():
  If Anthropic fails (every retry exhausted for call_llm(), or the stream
  failed to even open for stream_llm() — see stream_llm()'s docstring for
  why only "failed to open" triggers a streaming fallback, not a mid-stream
  drop), the call retries once against Gemini instead of giving up — but
  only when _gemini_fallback_eligible() says the request translates safely:

    - `tools`, if passed, must be plain custom function-tools (every tool
      dict has an "input_schema" key) — Anthropic *server-side* tools (e.g.
      `web_search_20260209`) have no Gemini equivalent this module builds,
      so a call using one is never eligible.
    - Every message's `content` must be either a plain string, or a list of
      blocks whose `type` is one of "text" / "tool_use" / "tool_result".
      Vision/PDF calls (block `type` "image"/"document") are NOT eligible —
      Anthropic's multi-modal content shape has no translation here.
    - stream_llm() additionally requires `tools is None` — Gemini function
      calls don't stream incrementally the way Anthropic's do, so a
      streaming tool-use turn is never eligible; only the final, tool-free
      streaming reply in a tool-loop conversation can fall back.

  Ineligible or doubly-failing calls raise the original Anthropic
  LLMCallError, exactly as before this fallback existed — nothing regresses
  for callers that don't hit the fallback path.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, AsyncIterator, Optional

import anthropic
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from backend.config import ANTHROPIC_API_KEY, GEMINI_API_KEY

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

# ── Gemini fallback client ──────────────────────────────────────────────────────
# None when GEMINI_API_KEY is unset — every fallback attempt checks this
# first, so "no Gemini key configured" fails exactly like "no fallback
# exists" (raises the original Anthropic LLMCallError), never a second error
# about the fallback itself being unconfigured.
_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Single fixed fallback model — this is a reliability net, not a tuned
# per-call-site choice, so one reasonably fast/capable default is used for
# every fallback call regardless of which Claude model was originally
# requested.
_GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

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
    raw: Any                       # full anthropic.types.Message (or a duck-typed
                                    # equivalent — see _GeminiRaw — for a Gemini
                                    # fallback response)


# ── Gemini eligibility + translation ─────────────────────────────────────────────
#
# Anthropic's wire format is the one true shape every call site and every
# multi-turn tool loop (chat.py's _ariel_tool_loop_then_stream) builds and
# reads. These helpers translate FROM that shape TO Gemini's, and translate
# Gemini's response BACK INTO Anthropic-shaped objects — so a tool loop that
# falls back to Gemini for one turn, then back to Anthropic (or Gemini again)
# for the next, never needs its own bookkeeping to change: it always reads
# and writes Anthropic shapes, and each call_llm() invocation re-translates
# fresh, statelessly, in whichever direction is needed for that one call.

_ELIGIBLE_BLOCK_TYPES = {"text", "tool_use", "tool_result"}


def _content_eligible(content: Any) -> bool:
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return all(isinstance(b, dict) and b.get("type") in _ELIGIBLE_BLOCK_TYPES for b in content)
    return False


def _tools_eligible(tools: Optional[list]) -> bool:
    """Only plain custom function-tools translate — Anthropic server-side
    tools (web_search, etc.) have no "input_schema" and no Gemini equivalent
    built here."""
    if tools is None:
        return True
    return all(isinstance(t, dict) and "input_schema" in t for t in tools)


def _gemini_fallback_eligible(messages: list[dict], tools: Optional[list]) -> bool:
    if _gemini_client is None or not _tools_eligible(tools):
        return False
    return all(_content_eligible(m.get("content")) for m in messages)


class _FakeContentBlock:
    """
    Duck-types an Anthropic content block closely enough for
    chat.py's _ariel_tool_loop_then_stream(): `.type` plus whichever of
    `.text` / `.id` / `.name` / `.input` apply, and `.model_dump()` returning
    the same plain-dict shape Anthropic's own pydantic blocks produce (the
    loop round-trips prior-turn blocks into the next turn's `messages` via
    `.model_dump()`).
    """

    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

    def model_dump(self) -> dict:
        return dict(self._data)


def _messages_to_gemini_contents(messages: list[dict]) -> list[genai_types.Content]:
    """
    Anthropic messages (str content, or block-list content with text/
    tool_use/tool_result blocks) -> Gemini `contents`. Tool correlation:
    Anthropic's tool_result blocks reference the producing tool_use's `id`;
    Gemini's function_response correlates by `name` instead, so this walks
    messages in order building an id->name map from tool_use blocks seen so
    far, exactly the order they'd have been appended in a real conversation.
    """
    contents: list[genai_types.Content] = []
    tool_id_to_name: dict[str, str] = {}

    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        content = m["content"]

        if isinstance(content, str):
            contents.append(genai_types.Content(role=role, parts=[genai_types.Part(text=content)]))
            continue

        parts: list[genai_types.Part] = []
        for block in content:
            btype = block["type"]
            if btype == "text":
                parts.append(genai_types.Part(text=block["text"]))
            elif btype == "tool_use":
                tool_id_to_name[block["id"]] = block["name"]
                parts.append(genai_types.Part.from_function_call(
                    name=block["name"], args=block.get("input") or {},
                ))
            elif btype == "tool_result":
                name = tool_id_to_name.get(block["tool_use_id"], "unknown_tool")
                parts.append(genai_types.Part.from_function_response(
                    name=name, response={"result": block.get("content")},
                ))
        contents.append(genai_types.Content(role=role, parts=parts))

    return contents


def _anthropic_tools_to_gemini(tools: Optional[list]) -> Optional[genai_types.Tool]:
    if not tools:
        return None
    declarations = [
        genai_types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters_json_schema=t.get("input_schema"),
        )
        for t in tools
    ]
    return genai_types.Tool(function_declarations=declarations)


def _gemini_response_to_content_blocks(response: genai_types.GenerateContentResponse) -> list[_FakeContentBlock]:
    """Gemini's response parts -> Anthropic-shaped content blocks (text /
    tool_use), so callers reading `.raw.content` see the same block shapes
    regardless of which provider actually answered."""
    blocks: list[_FakeContentBlock] = []
    candidates = getattr(response, "candidates", None) or []
    parts = candidates[0].content.parts if candidates and candidates[0].content else []
    for part in parts or []:
        if getattr(part, "function_call", None) is not None:
            fc = part.function_call
            blocks.append(_FakeContentBlock(
                type="tool_use",
                id=f"gemini_{uuid.uuid4().hex[:12]}",
                name=fc.name,
                input=dict(fc.args) if fc.args else {},
            ))
        elif getattr(part, "text", None):
            blocks.append(_FakeContentBlock(type="text", text=part.text))
    return blocks


def _gemini_generation_config(
    *, max_tokens: int, system: Optional[str], temperature: Optional[float], tools: Optional[list],
) -> genai_types.GenerateContentConfig:
    kwargs: dict = {"max_output_tokens": max_tokens}
    if system is not None:
        kwargs["system_instruction"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    gemini_tool = _anthropic_tools_to_gemini(tools)
    if gemini_tool is not None:
        kwargs["tools"] = [gemini_tool]
    return genai_types.GenerateContentConfig(**kwargs)


async def _call_gemini(
    *,
    system: Optional[str],
    messages: list[dict],
    max_tokens: int,
    purpose: str,
    user_id: Optional[str],
    job_id: Optional[str],
    temperature: Optional[float],
    tools: Optional[list],
    timeout: float,
) -> LLMResult:
    """
    Single-attempt Gemini fallback call. Only reached from call_llm() after
    every Anthropic attempt has already failed and _gemini_fallback_eligible()
    passed. Raises LLMCallError on failure — same safe-wrapping contract as
    the Anthropic path, never leaks raw provider exception text.
    """
    contents = _messages_to_gemini_contents(messages)
    config = _gemini_generation_config(
        max_tokens=max_tokens, system=system, temperature=temperature, tools=tools,
    )

    start = time.monotonic()
    try:
        response = await _gemini_client.aio.models.generate_content(
            model=_GEMINI_FALLBACK_MODEL, contents=contents, config=config,
        )
    except genai_errors.APIError as exc:
        logger.error(
            "[llm_client] purpose=%s GEMINI FALLBACK FAILED %s (status=%s)",
            purpose, type(exc).__name__, getattr(exc, "code", None),
        )
        raise LLMCallError(
            "The AI service is temporarily unavailable. Please try again shortly."
        ) from exc
    except Exception as exc:
        logger.exception(
            "[llm_client] purpose=%s GEMINI FALLBACK UNEXPECTED %s", purpose, type(exc).__name__,
        )
        raise LLMCallError(
            "An unexpected error occurred while contacting the AI service."
        ) from exc

    latency_ms = (time.monotonic() - start) * 1000
    usage = response.usage_metadata
    input_tokens = getattr(usage, "prompt_token_count", None) if usage is not None else None
    output_tokens = getattr(usage, "candidates_token_count", None) if usage is not None else None

    logger.info(
        "[llm_client] purpose=%s model=%s (GEMINI FALLBACK) user_id=%s job_id=%s "
        "input_tokens=%s output_tokens=%s latency_ms=%.0f",
        purpose, _GEMINI_FALLBACK_MODEL, user_id, job_id, input_tokens, output_tokens, latency_ms,
    )

    blocks = _gemini_response_to_content_blocks(response)
    text = blocks[0].text if blocks and blocks[0].type == "text" else ""

    return LLMResult(
        text=text,
        model=_GEMINI_FALLBACK_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        attempts=1,
        raw=SimpleNamespace(content=blocks),
    )


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
    Make one non-streaming LLM call with timeout, transient-failure retry,
    safe metadata-only logging, and an automatic Gemini fallback (see the
    module docstring) if every Anthropic attempt fails.

    `purpose` / `user_id` / `job_id` are for server-side log correlation
    ONLY. They are never sent to the provider and never appear in `system`
    or `messages` — callers must not fold them into the prompt themselves
    expecting this function to do it; it doesn't.

    `tools` is passed straight through to messages.create() unchanged (e.g.
    Anthropic server-side tools like web_search) — callers driving a
    multi-turn tool/pause_turn loop should call call_llm() once per turn and
    inspect `.raw.stop_reason` / `.raw.content` themselves; this function
    always makes exactly one Anthropic call per invocation (plus, on
    failure, at most one Gemini fallback call). See _gemini_fallback_eligible()
    for exactly which `tools` values are translatable.

    Never logs: system, messages, prompt content, or any field of the
    response other than token counts. Raises LLMCallError on failure —
    never re-raises the raw provider exception to the caller.
    """
    try:
        return await _call_anthropic(
            system=system, messages=messages, model=model, max_tokens=max_tokens,
            purpose=purpose, user_id=user_id, job_id=job_id, temperature=temperature,
            tools=tools, timeout=timeout, max_retries=max_retries,
        )
    except LLMCallError:
        if not _gemini_fallback_eligible(messages, tools):
            raise
        logger.warning(
            "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
            "Anthropic exhausted — falling back to Gemini (%s)",
            purpose, model, user_id, job_id, _GEMINI_FALLBACK_MODEL,
        )
        return await _call_gemini(
            system=system, messages=messages, max_tokens=max_tokens, purpose=purpose,
            user_id=user_id, job_id=job_id, temperature=temperature, tools=tools, timeout=timeout,
        )


async def _call_anthropic(
    *,
    system: Optional[str],
    messages: list[dict],
    model: str,
    max_tokens: int,
    purpose: str,
    user_id: Optional[str],
    job_id: Optional[str],
    temperature: Optional[float],
    tools: Optional[list],
    timeout: float,
    max_retries: int,
) -> LLMResult:
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


async def _gemini_text_stream_events(
    gemini_stream: AsyncIterator[genai_types.GenerateContentResponse],
) -> AsyncIterator[SimpleNamespace]:
    """
    Adapts a Gemini streaming iterator into the same event shape chat.py's
    stream consumers already read off a raw Anthropic stream:
    content_block_start -> content_block_delta* -> content_block_stop.
    Text-only (no function-call parts — see stream_llm()'s tools-excluded
    eligibility rule, this is never reached for a tool-using turn).
    """
    yield SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text"))
    async for chunk in gemini_stream:
        if chunk.text:
            yield SimpleNamespace(
                type="content_block_delta",
                delta=SimpleNamespace(type="text_delta", text=chunk.text),
            )
    yield SimpleNamespace(type="content_block_stop")


@asynccontextmanager
async def stream_llm(
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
    Async context manager wrapping one streamed turn, built from the shared
    centralized Anthropic client, with a Gemini fallback if the Anthropic
    stream fails to even open (auth error, missing key, connection refused
    before any bytes arrive).

    Usage is unchanged from the plain-factory version this replaced:
    `async with stream_llm(...) as stream: async for event in stream: ...`
    — `stream_llm(...)` still returns immediately (no coroutine runs until
    entered), so no call site needed to change.

    Why only "failed to open", not mid-stream failures: once Anthropic has
    already started sending bytes to the client, silently switching provider
    mid-response could duplicate or garble text already shown to the user.
    The caller's own try/except around its `async for` loop still handles a
    genuine mid-stream drop exactly as before — this function does not
    catch or translate those.

    The Gemini fallback here is TEXT-ONLY: it requires `tools is None` (in
    addition to _gemini_fallback_eligible()'s usual message-content check),
    because Gemini's function calls don't arrive as an incremental JSON
    stream the way Anthropic's do — there is no incremental-tool-call event
    shape to adapt here. A tool-using stream that fails to open just raises,
    same as before this fallback existed.

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

    eligible = tools is None and _gemini_fallback_eligible(messages, None)
    anthropic_cm = _client.messages.stream(timeout=timeout, **kwargs)
    try:
        anthropic_stream = await anthropic_cm.__aenter__()
    except Exception:
        if not eligible:
            raise
        logger.warning(
            "[llm_client] purpose=%s model=%s user_id=%s job_id=%s "
            "Anthropic stream failed to open — falling back to Gemini streaming (%s)",
            purpose, model, user_id, job_id, _GEMINI_FALLBACK_MODEL,
        )
        contents = _messages_to_gemini_contents(messages)
        config = _gemini_generation_config(
            max_tokens=max_tokens, system=system, temperature=temperature, tools=None,
        )
        gemini_stream = await _gemini_client.aio.models.generate_content_stream(
            model=_GEMINI_FALLBACK_MODEL, contents=contents, config=config,
        )
        yield _gemini_text_stream_events(gemini_stream)
        return

    try:
        yield anthropic_stream
    finally:
        await anthropic_cm.__aexit__(None, None, None)
