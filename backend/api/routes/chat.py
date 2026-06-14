"""
Chat API — streaming assistant endpoints.

POST /api/chat/stream
  Body:  { messages: [{role, content}], job_context: {topic, job_title?, company?} | null }
  Returns: text/event-stream  (SSE)

POST /api/chat/ariel/private
  Body:  { message: str, chat_history: [{role, content}] }
  Returns: text/event-stream  (SSE)

  Ariel's private authenticated endpoint.  Dynamically selects between two
  system-prompt modes based on the user's onboarding_status in master_profiles:

    "incomplete" → Data Collection Interviewer mode
      Ariel asks behavioural drill-down questions to collect skills, KPIs, and
      experience.  She calls ARIEL_TOOLS silently to persist every fact the user
      reveals.  Tool calls are executed server-side in a loop before the final
      text response is streamed to the client.

    "complete" → Career Strategist mode
      Ariel receives the full master_profile JSON.  She analyses gaps, suggests
      career moves, and stops asking for basic background already on file.

SSE event format (both endpoints)
----------------------------------
  data: {"chunk": "<text>"}\n\n   — text delta
  data: [DONE]\n\n               — stream complete
  data: {"error": "<msg>"}\n\n   — fatal error
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, List, Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import CurrentUser, get_current_user
from backend.services.db import ENGINE, MasterProfileRow
from backend.agents.ariel_tools import ARIEL_TOOLS, execute_tool

logger = logging.getLogger(__name__)
router = APIRouter()

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 1024

# ── API key guard ──────────────────────────────────────────────────────────────
# Check once at module load so the first request to any chat endpoint returns a
# clear 503 rather than a cryptic AuthenticationError deep in the Anthropic SDK.
_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not _ANTHROPIC_KEY or not _ANTHROPIC_KEY.startswith("sk-ant-"):
    logger.warning(
        "[chat] ANTHROPIC_API_KEY is missing or malformed — all chat endpoints "
        "will return 503 until the key is set in backend/.env and the server "
        "is restarted."
    )

def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Return a client, or raise HTTPException 503 when the key is absent."""
    if not _ANTHROPIC_KEY or not _ANTHROPIC_KEY.startswith("sk-ant-"):
        raise HTTPException(
            status_code=503,
            detail=(
                "AI service unavailable: ANTHROPIC_API_KEY is not configured. "
                "Add the key to backend/.env and restart the server."
            ),
        )
    return anthropic.AsyncAnthropic(api_key=_ANTHROPIC_KEY)

# ── Tool definitions ───────────────────────────────────────────────────────────

_TOOLS: list[dict] = [
    {
        "name": "tailor_resume_for_job",
        "description": (
            "Trigger the CV tailoring pipeline for the current job. "
            "Call this when the user explicitly asks to tailor, update, or customise "
            "their CV/resume for the role being discussed. "
            "Do NOT call it for general advice questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_title": {
                    "type": "string",
                    "description": "The exact job title to tailor the CV for.",
                },
                "company": {
                    "type": "string",
                    "description": "The company name (empty string if unknown).",
                },
                "focus_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific skills or keywords the CV should emphasise, "
                        "drawn from the skill-gap context."
                    ),
                },
            },
            "required": ["job_title", "company", "focus_skills"],
        },
    }
]

# ── Request schema ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str

class JobContext(BaseModel):
    topic:     str
    job_title: Optional[str] = None
    company:   Optional[str] = None

class ChatStreamRequest(BaseModel):
    messages:    List[ChatMessage]
    job_context: Optional[JobContext] = None

# ── System prompt builder ──────────────────────────────────────────────────────

def _build_system_prompt(profile: dict, job_context: Optional[JobContext]) -> str:
    parts: list[str] = []

    parts.append(
        "You are a sharp, empathetic career assistant embedded inside JobApply, "
        "an AI-powered job search platform. Your role is to help the candidate "
        "address skill gaps, tailor their CV language, and prepare for interviews.\n\n"
        "Tone: concise, direct, and encouraging. Use bullet points for structured advice. "
        "Never fabricate experience — only reference what is in the candidate profile below."
    )

    # Inject job context when provided
    if job_context:
        ctx_parts: list[str] = [f"TOPIC: {job_context.topic}"]
        if job_context.job_title:
            ctx_parts.append(f"ROLE: {job_context.job_title}")
        if job_context.company:
            ctx_parts.append(f"COMPANY: {job_context.company}")
        parts.append("JOB CONTEXT\n" + "\n".join(ctx_parts))

    # Inject a condensed candidate profile so the model can reference real experience
    if profile:
        profile_lines: list[str] = ["CANDIDATE PROFILE (verified — use as ground truth)"]

        name = profile.get("name") or profile.get("full_name")
        if name:
            profile_lines.append(f"Name: {name}")

        current_title = profile.get("current_title") or profile.get("title")
        if current_title:
            profile_lines.append(f"Current title: {current_title}")

        experience: list[dict] = profile.get("experience") or []
        if experience:
            profile_lines.append("Experience (most recent first):")
            for exp in experience[:6]:  # cap at 6 to stay within context budget
                role    = exp.get("role") or exp.get("title", "?")
                company = exp.get("company", "?")
                dates   = exp.get("dates") or f"{exp.get('start_date','')}–{exp.get('end_date','')}"
                profile_lines.append(f"  • {role} @ {company} ({dates})")

        skills: list[str] = profile.get("skills") or []
        if isinstance(skills, list) and skills:
            # skills may be a flat list or a dict of categories
            if isinstance(skills[0], str):
                profile_lines.append(f"Skills: {', '.join(skills[:20])}")
            elif isinstance(skills[0], dict):
                flat = [s for cat in skills for s in (cat.get("items") or [])]
                profile_lines.append(f"Skills: {', '.join(flat[:20])}")

        education: list[dict] = profile.get("education") or []
        if education:
            degrees = [
                f"{e.get('degree') or e.get('certification','?')} from {e.get('institution','?')}"
                for e in education[:3]
            ]
            profile_lines.append(f"Education: {'; '.join(degrees)}")

        parts.append("\n".join(profile_lines))

    return "\n\n---\n\n".join(parts)

# ── SSE helpers ────────────────────────────────────────────────────────────────

def _sse(payload: str) -> str:
    """Wrap a payload string as a single SSE event."""
    return f"data: {payload}\n\n"

def _sse_chunk(text: str) -> str:
    return _sse(json.dumps({"chunk": text}))

def _sse_done() -> str:
    return _sse("[DONE]")

def _sse_error(msg: str) -> str:
    return _sse(json.dumps({"error": msg}))

def _sse_tool_call(name: str, input: dict) -> str:
    return _sse(json.dumps({"type": "tool_call", "name": name, "input": input}))

# ── Streaming generator ────────────────────────────────────────────────────────

async def _stream_response(
    messages:    List[ChatMessage],
    system:      str,
    client:      anthropic.AsyncAnthropic,
) -> AsyncIterator[str]:
    """
    Stream claude-sonnet-4-6 replies as SSE.

    Iterates raw stream events so we can handle both text deltas and tool-use
    blocks in a single pass:

      text delta      → data: {"chunk": "<text>"}
      tool_use block  → data: {"type": "tool_call", "name": "...", "input": {...}}
      end of stream   → data: [DONE]
    """
    try:
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant") and m.content.strip()
        ]

        if not api_messages or api_messages[-1]["role"] != "user":
            yield _sse_error("No user message to respond to.")
            return

        # Accumulator for the tool-use block that is currently being streamed.
        # The SDK delivers tool input as a sequence of partial JSON strings via
        # input_json_delta events, so we buffer them and parse once the block closes.
        pending_tool_name: Optional[str]  = None
        pending_tool_json: str            = ""

        async with client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=api_messages,
            tools=_TOOLS,
        ) as stream:
            async for event in stream:
                etype = event.type

                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        pending_tool_name = block.name
                        pending_tool_json = ""

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta" and delta.text:
                        yield _sse_chunk(delta.text)
                    elif delta.type == "input_json_delta":
                        pending_tool_json += delta.partial_json

                elif etype == "content_block_stop":
                    if pending_tool_name:
                        try:
                            tool_input = json.loads(pending_tool_json) if pending_tool_json else {}
                        except json.JSONDecodeError:
                            tool_input = {}
                        yield _sse_tool_call(pending_tool_name, tool_input)
                        pending_tool_name = None
                        pending_tool_json = ""

        yield _sse_done()

    except anthropic.APIStatusError as exc:
        logger.error("[chat/stream] Anthropic API error: %s", exc)
        yield _sse_error(f"AI service error ({exc.status_code}). Please try again.")
    except Exception as exc:
        logger.exception("[chat/stream] Unexpected error")
        yield _sse_error("An unexpected error occurred. Please try again.")

# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream an AI assistant reply as SSE.

    The client sends the full conversation history (user + assistant turns only)
    plus an optional job_context object. The server builds a system prompt from
    the user's master profile and the job context, then streams Claude's reply.
    """
    print(f"=== DEBUG [chat/stream] user={user.user_id}  msgs={len(body.messages)}  job_context={body.job_context} ===")

    # Load the authenticated user's master profile (graceful fallback to empty dict)
    profile: dict = {}
    try:
        from backend.services.user_profile_store import load as _load_profile
        profile = _load_profile(user.user_id) or {}
    except Exception as exc:
        logger.warning("[chat/stream] Could not load profile for %s: %s", user.user_id, exc)

    system = _build_system_prompt(profile, body.job_context)
    client = _get_anthropic_client()

    return StreamingResponse(
        _stream_response(body.messages, system, client),
        media_type="text/event-stream",
        headers={
            # Prevent proxy / CDN buffering — critical for SSE to work end-to-end
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/chat/ariel/private
# ═══════════════════════════════════════════════════════════════════════════════

_ARIEL_MODEL      = "claude-sonnet-4-6"
_ARIEL_MAX_TOKENS = 1024
_MAX_TOOL_LOOPS   = 5   # safety ceiling on sequential tool-use iterations

# ── System prompt builders ────────────────────────────────────────────────────

_ARIEL_INTERVIEWER_SYSTEM = """\
You are Ariel, a warm and incisive career intelligence assistant for JobApply.
You are in DATA COLLECTION mode. The user has not yet completed their professional \
profile. Your mission: extract a complete, structured professional history through \
natural, engaging conversation.

STRICT SCOPE — DEFLECT TECHNICAL SUPPORT:
You are a career agent, not a technical support agent. If the user asks anything \
outside career development — such as password resets, billing questions, login \
issues, account settings, bug reports, or any platform technical question — \
respond with exactly: "I'm focused on your career path. Please ask Eliya in the \
Help chat for technical support." Then return the conversation to profile building.

OBJECTIVES (cover all before declaring done):
  1. Work experience — every role: company, title, dates, 2-4 bullet achievements \
with measurable outcomes (numbers, percentages, team sizes).
  2. Skills — technical tools, methodologies, soft skills. Do not accept vague \
answers; probe for specific tool names and proficiency levels.
  3. Education — degree, institution, graduation year.
  4. Career goals — target roles, preferred locations, work environment, notes.

BEHAVIOUR:
  • Acknowledge what the user shared in 1-2 sentences, then ask exactly ONE \
focused follow-up question. Never ask two questions in the same message.
  • Use the CRUD tools silently after every user turn to persist what they shared. \
Do not announce tool calls to the user — just do them invisibly.
  • When you are certain the user has nothing more to add and they confirm it \
explicitly (e.g. "That's everything", "We're done"), call finalize_onboarding.
  • Plain text only. No markdown, no asterisks, no bullet symbols in your replies.
  • Respond in the user's language (English or Hebrew).
"""

def _build_ariel_strategist_system(master_profile: dict) -> str:
    profile_json = json.dumps(master_profile, ensure_ascii=False, indent=2)
    return f"""\
You are Ariel, a sharp and empathetic career strategist embedded in JobApply.
You are in CAREER STRATEGIST mode. The user's profile is fully collected and \
verified. You have complete context — do NOT ask for basic background the profile \
already contains.

STRICT SCOPE — DEFLECT TECHNICAL SUPPORT:
You are a career strategist, not a technical support agent. If the user asks \
anything outside career development — such as password resets, billing questions, \
login issues, account settings, or bug reports — respond with exactly: \
"I'm focused on your career path. Please ask Eliya in the Help chat for technical \
support." Then return the conversation to career strategy.

YOUR ROLE:
  • Analyse skill gaps between the user's profile and target roles.
  • Suggest specific, actionable career moves (roles, companies, skill upgrades).
  • Help tailor CV language, prepare interview answers, and craft outreach messages.
  • Reference actual facts from the profile below — never fabricate experience.

TONE: Direct, concise, and genuinely encouraging. Use plain text only. \
Respond in the user's language.

MASTER PROFILE (ground truth — verified):
{profile_json}
"""

# ── Tool-loop + streaming pipeline ───────────────────────────────────────────

async def _ariel_tool_loop_then_stream(
    messages:       list[dict[str, Any]],
    system:         str,
    client:         anthropic.AsyncAnthropic,
    user_id:        str,
    db_session:     Session,
) -> AsyncIterator[str]:
    """
    Execute the Ariel pipeline as an SSE generator:

      1. Make a synchronous Anthropic call (no streaming) to handle tool use.
         Repeat until the model returns no tool_use blocks (up to _MAX_TOOL_LOOPS).
      2. Once tools are exhausted, make a final streaming call and yield each
         text delta as an SSE chunk so the frontend receives a live stream.

    The two-phase approach (sync loop → streaming final) is necessary because
    streaming and multi-step tool execution cannot be interleaved cleanly in a
    single pass: you cannot both buffer tool-input JSON and stream text at the
    same time without a stateful coroutine that the SDK does not expose.

    The client never sees intermediate tool-execution; they only see the final
    conversational reply stream.
    """
    loop_messages = list(messages)   # local copy we append to during the loop

    # ── Phase 1: synchronous tool-use loop ────────────────────────────────────
    for loop_idx in range(_MAX_TOOL_LOOPS):
        try:
            response = await client.messages.create(
                model      = _ARIEL_MODEL,
                max_tokens = _ARIEL_MAX_TOKENS,
                system     = system,
                messages   = loop_messages,
                tools      = ARIEL_TOOLS,
            )
        except anthropic.APIStatusError as exc:
            logger.error("[ariel/private] Anthropic API error in tool loop: %s", exc)
            yield _sse_error(f"AI service error ({exc.status_code}). Please try again.")
            return
        except Exception as exc:
            logger.exception("[ariel/private] Unexpected error in tool loop")
            yield _sse_error("An unexpected error occurred. Please try again.")
            return

        # Partition response blocks
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks     = [b for b in response.content if b.type == "text"]

        if not tool_use_blocks:
            # No more tool calls — the text in this response is the final reply.
            # Emit it as SSE chunks so the frontend receives a stream, then break.
            for block in text_blocks:
                text = getattr(block, "text", "") or ""
                if text:
                    # Chunk into ~80-char pieces so the client renders progressively
                    for i in range(0, len(text), 80):
                        yield _sse_chunk(text[i:i + 80])
            yield _sse_done()
            return

        # Execute every tool the model requested in this turn
        tool_results: list[dict[str, Any]] = []
        for tu in tool_use_blocks:
            logger.info(
                "[ariel/private] tool_use loop=%d tool=%s user=%s",
                loop_idx, tu.name, user_id,
            )
            result_text = execute_tool(tu.name, tu.input, user_id, db_session)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tu.id,
                "content":     result_text,
            })

        # Append the assistant turn (with tool_use blocks) and the tool results
        loop_messages.append({
            "role":    "assistant",
            "content": [b.model_dump() for b in response.content],
        })
        loop_messages.append({
            "role":    "user",
            "content": tool_results,
        })

    # ── Phase 2: final streaming call after all tool loops ────────────────────
    # Reached only when the model kept requesting tools up to _MAX_TOOL_LOOPS.
    # Make one final streaming call with tool_choice=none to force a text reply.
    try:
        async with client.messages.stream(
            model       = _ARIEL_MODEL,
            max_tokens  = _ARIEL_MAX_TOKENS,
            system      = system,
            messages    = loop_messages,
            tool_choice = {"type": "none"},
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta" and delta.text:
                        yield _sse_chunk(delta.text)
        yield _sse_done()
    except anthropic.APIStatusError as exc:
        logger.error("[ariel/private] Anthropic API error in final stream: %s", exc)
        yield _sse_error(f"AI service error ({exc.status_code}). Please try again.")
    except Exception:
        logger.exception("[ariel/private] Unexpected error in final stream")
        yield _sse_error("An unexpected error occurred. Please try again.")


# ── Request schema ────────────────────────────────────────────────────────────

class ArielPrivateRequest(BaseModel):
    message:      str
    chat_history: List[ChatMessage] = []


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/ariel/private")
async def ariel_private(
    body: ArielPrivateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Ariel's authenticated private chat endpoint.

    Dynamically selects the system prompt based on the user's onboarding_status:
      • "incomplete" → Data Collection Interviewer (uses ARIEL_TOOLS to persist facts)
      • "complete"   → Career Strategist (receives full master_profile as context)

    Tool calls are executed server-side in a loop before the final text response
    is streamed to the frontend — the client only receives text chunks, never raw
    tool payloads.
    """
    print(f"=== DEBUG [chat/ariel/private] user={user.user_id}  msg_len={len(body.message)}  history={len(body.chat_history)} ===")

    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty.")

    # ── Load master profile and onboarding status ─────────────────────────────
    db_session     = Session(ENGINE)
    onboarding     = "incomplete"
    master_profile: dict = {}

    try:
        row = db_session.get(MasterProfileRow, user.user_id)
        if row:
            onboarding     = row.onboarding_status or "incomplete"
            master_profile = row.master_profile   or {}
    except Exception as exc:
        logger.warning(
            "[ariel/private] Could not load master profile for %s: %s", user.user_id, exc
        )

    # ── Build dynamic system prompt ───────────────────────────────────────────
    if onboarding == "complete":
        system = _build_ariel_strategist_system(master_profile)
        logger.info("[ariel/private] mode=strategist user=%s", user.user_id)
    else:
        system = _ARIEL_INTERVIEWER_SYSTEM
        logger.info("[ariel/private] mode=interviewer user=%s", user.user_id)

    # ── Build Anthropic messages array ────────────────────────────────────────
    # Validate history: only user/assistant turns with non-empty content,
    # alternating correctly (Anthropic requires strict user/assistant alternation).
    raw_history = [
        {"role": m.role, "content": m.content}
        for m in body.chat_history
        if m.role in ("user", "assistant") and m.content.strip()
    ]

    # Ensure the array ends with the new user message
    messages: list[dict[str, Any]] = [
        *raw_history,
        {"role": "user", "content": body.message.strip()},
    ]

    client = _get_anthropic_client()

    return StreamingResponse(
        _ariel_tool_loop_then_stream(messages, system, client, user.user_id, db_session),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
