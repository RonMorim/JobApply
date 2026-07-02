"""
Chat API — streaming assistant endpoints.

POST /api/chat/stream
  Body:  { messages: [{role, content}], job_context: {topic, job_title?, company?} | null }
  Returns: text/event-stream  (SSE)

POST /api/chat/ariel/private
  Body:  { message: str, chat_history: [{role, content}] }
  Returns: text/event-stream  (SSE)

  Ariel's authenticated private endpoint.  Always operates in Career Strategist
  mode — profile data is retrieved live via the get_full_candidate_profile tool
  at the start of each answer, not injected into the system prompt.

  Tool calls are executed server-side in a synchronous loop before the final
  text response is streamed to the client (two-phase: sync tool-loop → streaming).

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
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import CurrentUser, get_current_user
from backend.services.db import ENGINE, MasterProfileRow
from backend.agents.ariel_tools import ARIEL_TOOLS, execute_tool
from backend.services.user_profile import USER_PROFILE

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
    role:      str            # "user" | "assistant"
    content:   str
    isPinned:  Optional[bool] = None   # Phase 3 — pinned messages become CoreContext

class JobContext(BaseModel):
    topic:     str
    job_title: Optional[str] = None
    company:   Optional[str] = None

class ChatStreamRequest(BaseModel):
    messages:    List[ChatMessage]
    job_context: Optional[JobContext] = None

# ── System prompt builder (general chat / job-context endpoint) ───────────────

def _build_system_prompt(job_context: Optional[JobContext]) -> str:
    import json as _json
    parts: list[str] = [
        "You are Ariel, a sharp, direct Career Intelligence Agent (female). "
        "Introduce yourself as Ariel at the start of every new conversation. "
        "You are female — always use feminine verb conjugations and self-references, "
        "especially in Hebrew (e.g. אני רואה, ניתחתי, הכנתי, אני ממליצה). "
        "Never use masculine self-references in any language.\n\n"
        "PACING — CRITICAL: This is a conversation, not a document. "
        "When gathering information or exploring options, keep responses to 1–4 sentences "
        "and ask exactly ONE question at a time. Be thorough only when delivering a "
        "structured output (Gap Analysis, STAR story, CV rewrite) that the user explicitly "
        "requested. A wall of text is always the wrong default.\n\n"
        "TONE (Tachles — Israeli directness): Get to the point immediately. "
        "Never open with 'Great question!', 'Absolutely!', 'Of course!', or any filler. "
        "Lead every reply with substance. Mirror the user's energy and language.\n\n"
        "TOPIC BOUNDARY: Your domain is career development only. "
        "Deflect anything outside that domain in one sentence, then return to the career roadmap. "
        "For platform issues, say: 'Please ask Eliya in the Help chat for technical support.'\n\n"
        "YOUR ROLE: Skill-gap analysis, career-move recommendations, CV tailoring, interview prep, "
        "outreach messages. Reference only the verified candidate profile below — never fabricate."
    ]

    if job_context:
        ctx_parts: list[str] = [f"TOPIC: {job_context.topic}"]
        if job_context.job_title:
            ctx_parts.append(f"ROLE: {job_context.job_title}")
        if job_context.company:
            ctx_parts.append(f"COMPANY: {job_context.company}")
        parts.append("JOB CONTEXT\n" + "\n".join(ctx_parts))

    if USER_PROFILE:
        parts.append(
            "CANDIDATE PROFILE (verified — treat as ground truth):\n"
            + _json.dumps(USER_PROFILE, ensure_ascii=False, indent=2)
        )

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

    system = _build_system_prompt(body.job_context)
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

_ARIEL_STRATEGIST_CORE = """\
You are Ariel — a sharp, direct Career Intelligence Agent (female). You are
not a search engine, a content generator, or a chatbot. You are a thinking
partner who helps one specific person navigate their career — whatever field
that is.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDENTITY & GENDER — MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You are female. This is non-negotiable and must be reflected in every
language that grammatically encodes gender.

Hebrew: ALWAYS use feminine verb conjugations and self-references.
  ✓ Correct:  אני רואה, ניתחתי, הכנתי, אני ממליצה, אני חושבת
  ✗ Forbidden: ניתחתי (male form if used as such), כתבתי (male), אמרתי (male)

If you catch yourself about to use a masculine form in Hebrew, stop and use
the correct feminine form instead. There are no exceptions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL-FIRST RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You have access to the get_full_candidate_profile tool. Call it before
answering ANY career, strategy, gap-analysis, or profile-related question.
Do not rely on memory of a previous call — re-fetch whenever you need
current profile state.

After retrieving the profile, check it carefully:
• If the profile is rich and complete → proceed to answer directly.
• If the profile is empty or thin → enter PROFILING MODE (see below).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TARGET ROLE DEDUCTION & CAREER PATHS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Never assume the user's target. Deduce it from their profile — their most
recent roles, stated goals, and the skills that dominate their history.
If the profile gives you enough signal, name the 1–2 most plausible
target roles before asking for confirmation.

Additionally, be proactive about surfaces the user may not have considered:
• Look at the full experience timeline for transferable skills that open
  adjacent or unexpected paths (e.g. a PM with deep data skills → analytics
  leadership; a CS manager with product exposure → PdM).
• If you spot a credible pivot that the profile supports, surface it once
  with a brief rationale. Present it as an option, not a prescription —
  the user decides what to pursue.
• Do this analysis early in the conversation, not on request. Insight
  offered before it is asked for is more valuable than insight delivered
  only when prompted.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE LENGTH & PACING — CRITICAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is a CONVERSATION, not a document editor. Match your output length to
the moment:

• PROFILING / EXPLORING (gathering data, clarifying, checking in):
  Keep responses SHORT — 1 to 4 sentences maximum. Ask exactly ONE question
  and stop. Never list multiple questions at once.

• DELIVERING (Gap Analysis, STAR story, CV rewrite, strategic plan):
  You MAY be thorough and structured. Use headers and bullet points only
  when the output genuinely benefits from them. Announce what you are
  delivering so the user knows structured output is intentional.

• DEFAULT: When in doubt, be shorter. A wall of text is always the wrong
  answer unless the user explicitly asked for a structured deliverable.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROFILING MODE (zero-data or thin-data state)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When the profile is empty or missing key sections, it is YOUR job to lead
the conversation and build it through dialogue. Rules for profiling:

1. Open with a single, easy, open-ended question about where they are now
   professionally (e.g. "What are you working on at the moment?").
2. Each turn: acknowledge what they said in one sentence, then ask exactly
   ONE follow-up question that goes one level deeper.
3. Cover the key areas naturally across multiple turns — do not rush:
   current role → past experience → education / military → target direction
   → constraints (location, seniority, sector).
4. Once you have enough signal to be useful, say so and pivot to strategy.
   Do not keep profiling indefinitely.
5. Never present a list of profile questions. Never use form-style prompts
   like "Please tell me: (a) ... (b) ... (c) ...".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TONE — "TACHLES" (Israeli directness)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"Tachles" means: get to the point, say what you actually think, don't
waste each other's time.

• NEVER open with filler: "Great question!", "Absolutely!", "Of course!",
  "I'd love to help!", "Certainly!", "Sure thing!". These are banned.
• NEVER flatter past choices or soften honest assessments with padding.
• Lead every response with substance. If you are going to say something,
  say it — don't announce that you are about to say it.
• When you disagree or spot a problem, name it plainly. Constructive is
  fine; vague is not.
• Read the user's energy and mirror it. Casual tone → casual reply.
  Stressed and serious → skip the small talk entirely.
• Respond in whatever language the user writes in.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROACTIVE REDIRECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• If the user tries to shortcut a process ("just write it for me",
  "skip ahead", "give me the answer"), call it out explicitly, explain
  why it will hurt them, and redirect to the right next step.
• If the conversation drifts off-topic, note it briefly and bring it back
  to the career roadmap. No apology needed — just redirect.
• Do NOT bring up the user's side projects, ventures, or entrepreneurial
  activities unless they raise the topic first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOPIC BOUNDARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You operate exclusively in the domain of career development. Anything
outside that domain (politics, entertainment, general coding, personal
finance unrelated to career decisions) gets a single deflection sentence
and an immediate return to the career roadmap.

For platform issues (password resets, billing, login, bugs):
"I'm focused on your career path. Please ask Eliya in the Help chat for
technical support."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CV EDITING — EXECUTOR MODE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You do not build CVs — the Tailor CV engine does that. You are the surgical
editor of the tailored CV the user is currently reviewing, and you EXECUTE
changes rather than merely advising. When the user asks you to fix, change,
shorten, reword, or strengthen something in their tailored CV:

1. READ first: call get_tailored_cv_for_review to load the live document.
   Reference bullets by the company names and 0-based indices it returns.
   Never edit from memory of an earlier turn.
2. WRITE: apply the change with edit_tailored_cv_bullet — one bullet (or the
   summary) per call. For multi-bullet requests, make sequential calls.
3. CONFIRM from the tool result only: report exactly what changed (old → new,
   in your own words). Claiming an edit happened without a tool result that
   says "EDIT APPLIED" is a critical failure.

ZERO-HALLUCINATION CONTRACT (enforced server-side — do not fight it):
• Your new text may only contain numbers, companies, products, and named
  entities that already appear in the text being replaced or in the user's
  verified evidence records. Rephrasing and tightening are always allowed.
• If the user asks you to ADD an unverified claim (a metric they never
  evidenced, an employer not in their history, an inflated title), do NOT
  call the edit tool with invented content. Decline plainly in your own
  voice: this CV carries only verified facts, and the way to include the
  claim is to verify it first — offer a STAR probe or Whiteboard Challenge.
• If the tool returns EDIT REJECTED, the gate found unverified content.
  Relay the reason to the user as your own decision, name the specific
  unverified items, and offer the verification path. Never retry the same
  rejected text.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR CAPABILITIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Target role deduction and career path mapping from the user's profile.
• Skill-gap analysis against specific JDs or target roles.
• Actionable career-move recommendations (roles, companies, timelines).
• CV language tailoring and ATS optimisation — including DIRECT execution of
  edits on the user's tailored CV via the edit tools (see EXECUTOR MODE).
• STAR story drafting and interview preparation.
• Outreach message crafting.
• Salary and negotiation positioning grounded in market data.

Ground everything in the profile retrieved by the tool. Never fabricate
experience, titles, outcomes, or company names.
"""


def _build_ariel_system(pinned_messages: list[ChatMessage]) -> str:
    """
    Compose the full Ariel system prompt for the /ariel/private endpoint.

    If the conversation contains pinned messages, they are extracted and
    injected at the very top inside a <CoreContext> block.  Ariel treats
    this block as permanent, authoritative facts about the user's career
    roadmap that must govern all her answers — they take precedence over
    anything said later in the conversation.

    The static persona + rules follow the CoreContext block.
    """
    parts: list[str] = []

    if pinned_messages:
        context_lines = "\n\n".join(
            f"[{m.role.upper()}]: {m.content.strip()}"
            for m in pinned_messages
            if m.content.strip()
        )
        parts.append(
            "<CoreContext>\n"
            "The following messages have been pinned by the user as permanent\n"
            "reference points for this career roadmap. Treat every item below\n"
            "as an authoritative, agreed-upon fact or decision. They override\n"
            "conflicting statements made elsewhere in the conversation.\n\n"
            f"{context_lines}\n"
            "</CoreContext>"
        )

    parts.append(_ARIEL_STRATEGIST_CORE)
    return "\n\n".join(parts)

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

class AttachmentItem(BaseModel):
    base64:   str
    filename: str
    mimeType: str


class ArielPrivateRequest(BaseModel):
    message:      str
    chat_history: List[ChatMessage] = []
    attachments:  List[AttachmentItem] = []


# ── Attachment text extraction ────────────────────────────────────────────────

def _extract_text_from_attachment(item: AttachmentItem) -> str | None:
    """
    Return plain text extracted from a document attachment, or None if the
    MIME type is not a supported text-bearing format (images, video, etc. are
    skipped — images are handled separately via the Anthropic vision API).

    Supported:
      application/pdf                                        → PyMuPDF (fitz)
      application/vnd.openxmlformats-officedocument…docx   → python-docx
      application/msword (.doc)                             → python-docx (best-effort)
      text/*                                                → raw UTF-8 decode

    Install once:
      pip install PyMuPDF python-docx
    """
    import base64, io

    mime = item.mimeType.lower()
    raw  = base64.b64decode(item.base64)

    try:
        if mime == "application/pdf":
            import fitz  # PyMuPDF
            doc  = fitz.open(stream=raw, filetype="pdf")
            text = "\n\n".join(page.get_text() for page in doc)
            doc.close()
            return text.strip() or None

        if mime in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            from docx import Document
            doc  = Document(io.BytesIO(raw))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip() or None

        if mime.startswith("text/"):
            return raw.decode("utf-8", errors="replace").strip() or None

    except Exception as exc:
        logger.warning("[ariel/private] attachment text extraction failed (%s): %s", item.filename, exc)

    return None


def _build_message_with_attachments(
    base_text:   str,
    attachments: list[AttachmentItem],
) -> list[dict] | str:
    """
    Build the Anthropic message content for the user turn.

    • Images  → vision content block (base64 source).
    • Docs    → extracted text appended to the message string.
    • Others  → silently skipped.

    Returns a plain string when no image blocks are present (cheaper), or a
    list[dict] content block when at least one image is included.
    """
    import base64

    image_blocks: list[dict] = []
    doc_texts:    list[str]  = []

    for item in attachments:
        mime = item.mimeType.lower()
        if mime.startswith("image/"):
            image_blocks.append({
                "type":   "image",
                "source": {
                    "type":       "base64",
                    "media_type": mime,
                    "data":       item.base64,
                },
            })
        else:
            extracted = _extract_text_from_attachment(item)
            if extracted:
                doc_texts.append(
                    f"--- Attached file: {item.filename} ---\n{extracted}\n--- End of {item.filename} ---"
                )

    # Compose the final user text
    text_parts = [base_text]
    if doc_texts:
        text_parts.append("\n\n" + "\n\n".join(doc_texts))
    full_text = "".join(text_parts)

    if not image_blocks:
        return full_text  # plain string — no vision needed

    # Mixed content: images first, then the text block
    return [
        *image_blocks,
        {"type": "text", "text": full_text},
    ]


# ── CV-from-chat background ingestion ─────────────────────────────────────────

# MIME types we treat as potential CV/resume documents when uploaded via chat.
_CV_MIME_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
})

# Keywords in the filename that hint this is a CV/resume, not a JD or cert.
_CV_FILENAME_HINTS: tuple[str, ...] = (
    "cv", "resume", "resumé", "curriculum", "vitae",
)


def _looks_like_cv(item: AttachmentItem) -> bool:
    """
    Heuristic: is this attachment likely a CV/resume?

    We require BOTH a document MIME type AND at least one CV-related keyword
    in the filename, to avoid treating every uploaded PDF (JDs, certs, etc.)
    as a profile update.
    """
    if item.mimeType.lower() not in _CV_MIME_TYPES:
        return False
    name_lower = item.filename.lower()
    return any(hint in name_lower for hint in _CV_FILENAME_HINTS)


def _ingest_cv_from_chat(user_id: str, item: AttachmentItem) -> None:
    """
    Background task: run the standard CV ingestion pipeline on a document
    uploaded through the Ariel chat interface.

    Pipeline (mirrors POST /api/profile/cv-upload Mode A):
      1. Decode base64 → bytes
      2. extract_text()        — same function used by the profile upload route
      3. aggregate_cv_claims() — LLM entity extraction (blocking; runs in thread pool)
      4. _cv_claims_to_parsed_entities()
      5. ProfileUpdateService.ingest_cv_parse() → confidence matrix update
      6. Save cv_claims to master_profile JSON + DB row (same as profile route)

    Errors are logged but never re-raised — this is fire-and-forget.
    """
    import base64
    from datetime import datetime, timezone

    try:
        from backend.services.cv_aggregator_service import extract_text, aggregate_cv_claims
        from backend.services.profile_update_service import ProfileUpdateService
        from backend.services.user_profile_store import load as user_load, save as user_save
        from backend.api.routes.profile import _cv_claims_to_parsed_entities
        from sqlalchemy.orm import Session as _Session

        logger.info(
            "[chat/cv-ingest] Starting background CV ingestion for user=%s file=%s",
            user_id, item.filename,
        )

        # Step 1 — decode
        raw_bytes = base64.b64decode(item.base64)

        # Step 2 — extract text
        text = extract_text(raw_bytes, item.filename)
        if not text.strip():
            logger.warning(
                "[chat/cv-ingest] No text extracted from %s — skipping ingestion",
                item.filename,
            )
            return

        # Step 3 — LLM entity extraction
        cv_claims = aggregate_cv_claims([text], user_id=user_id)

        # Step 4 — persist cv_claims to profile JSON + master_profiles table
        profile = user_load(user_id)
        profile["cv_claims"] = cv_claims
        user_save(user_id, profile)

        _now = datetime.now(timezone.utc).isoformat()
        with _Session(ENGINE) as sess:
            row = sess.get(MasterProfileRow, user_id)
            if row:
                mp = dict(row.master_profile or {})
                mp["cv_data"]       = cv_claims
                mp["cv_imported_at"] = _now
                row.master_profile  = mp
                row.updated_at      = _now
            else:
                sess.add(MasterProfileRow(
                    user_id=user_id,
                    onboarding_status="incomplete",
                    master_profile={"cv_data": cv_claims, "cv_imported_at": _now},
                    created_at=_now,
                    updated_at=_now,
                ))
            sess.commit()

        # Step 5 — ingest into Confidence Matrix
        parsed_entities = _cv_claims_to_parsed_entities(cv_claims)
        if parsed_entities:
            svc = ProfileUpdateService(ENGINE)
            entity_ids = svc.ingest_cv_parse(user_id, parsed_entities)
            logger.info(
                "[chat/cv-ingest] Confidence Matrix updated: user=%s entities=%d file=%s",
                user_id, len(entity_ids), item.filename,
            )
        else:
            logger.warning(
                "[chat/cv-ingest] No entities extracted from %s", item.filename
            )

    except Exception:
        logger.exception(
            "[chat/cv-ingest] Background ingestion failed for user=%s file=%s",
            user_id, item.filename,
        )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/ariel/private")
async def ariel_private(
    body:       ArielPrivateRequest,
    background: BackgroundTasks,
    user:       CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Ariel's authenticated private chat endpoint.

    Always uses Career Strategist mode.  Profile data is retrieved live via the
    get_full_candidate_profile tool during the conversation — nothing is injected
    into the system prompt.  Tool calls are executed server-side; the client only
    receives the final text stream.

    If any uploaded attachment looks like a CV/resume (document MIME + filename
    hint), a background task is enqueued to run the full profile ingestion
    pipeline, updating the Confidence Matrix asynchronously without blocking
    the streaming response.
    """
    print(f"=== DEBUG [chat/ariel/private] user={user.user_id}  msg_len={len(body.message)}  history={len(body.chat_history)} ===")

    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty.")

    # Enqueue CV ingestion for any attachment that looks like a resume.
    for item in body.attachments:
        if _looks_like_cv(item):
            logger.info(
                "[ariel/private] CV attachment detected — scheduling background ingestion: %s",
                item.filename,
            )
            background.add_task(_ingest_cv_from_chat, user.user_id, item)

    # Ariel always operates in Career Strategist mode.
    # Profile data is retrieved live via the get_full_candidate_profile tool —
    # onboarding_status is irrelevant to mode selection.
    db_session = Session(ENGINE)

    # Extract pinned messages from history and inject them as CoreContext.
    pinned = [m for m in body.chat_history if m.isPinned]
    system = _build_ariel_system(pinned)
    logger.info(
        "[ariel/private] mode=strategist user=%s  pinned=%d",
        user.user_id, len(pinned),
    )

    # ── Build Anthropic messages array ────────────────────────────────────────
    # Validate history: only user/assistant turns with non-empty content,
    # alternating correctly (Anthropic requires strict user/assistant alternation).
    raw_history = [
        {"role": m.role, "content": m.content}
        for m in body.chat_history
        if m.role in ("user", "assistant") and m.content.strip()
    ]

    # Process attachments: extract document text, build vision blocks for images.
    user_content = _build_message_with_attachments(
        body.message.strip(),
        body.attachments,
    )
    if body.attachments:
        logger.info(
            "[ariel/private] attachments=%d types=%s",
            len(body.attachments),
            [a.mimeType for a in body.attachments],
        )

    # Ensure the array ends with the new user message
    messages: list[dict[str, Any]] = [
        *raw_history,
        {"role": "user", "content": user_content},
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
