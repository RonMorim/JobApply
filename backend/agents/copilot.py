"""
CopilotAgent — precision, targeted editor for an already-generated cv_data.

Takes the current cv_data JSON, a plain-English instruction from the user,
and the candidate's full Master Profile (USER_PROFILE) as additional context.

Always returns a structured result:
  {"status": "success"|"warning"|"rejected", "message": str|None, "cv_data": {...}}

- success:  edit applied; cv_data is the updated JSON.
- warning:  edit is possible but destructive; cv_data is unchanged; message explains.
- rejected: edit is impossible (hallucination / full rewrite); cv_data is unchanged.

The Master Profile enables restore/add operations: if the user asks to bring back an
experience that was omitted from the current cv_data (e.g. GO-OUT, Pitango), the agent
looks it up in the Master Profile and inserts it — this is NOT hallucination.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from backend.agents.tailor import _enforce_limits, _sanitize_ai_tells

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

logger = logging.getLogger(__name__)

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 4000

_SYSTEM_PROMPT = """\
You are a precision CV editor and reasoning agent. You receive a cv_data JSON,
a user instruction, and a MASTER PROFILE containing the candidate's full verified
work history. You MUST respond with this exact JSON wrapper — always, no exceptions,
no plain text outside it:

{
  "status":  "success" | "warning" | "rejected",
  "message": "<string or null>",
  "cv_data": { <the cv_data object> }
}

══════════════════════════════════════════
STATUS DECISION RULES
══════════════════════════════════════════

"success" — Normal targeted edit. Apply it. Set cv_data to the mutated JSON.
  message can be null.
  MINIMUM MUTATION: change only the field(s) the instruction targets.
  Every other field stays byte-for-byte identical to the input.

  RESTORE / ADD FROM MASTER PROFILE:
  If the user asks to restore, add back, or include an experience, skill,
  education, certification, or military service that is absent from the current
  cv_data, check the MASTER PROFILE provided below. If the requested content
  exists in the Master Profile, extract it faithfully and insert it into cv_data:
    • Experience: format as {"role", "company", "dates", "bullets": [str]}
      with 3–5 bullets of 60–240 chars each derived from the profile "details".
    • Education / certification: add to the "education" array.
    • Skill: add the item to the appropriate skill category.
    • Military service: ALWAYS placed in the TOP-LEVEL "military" key — NOT in
      the experience array. Format exactly as:
        "military": {"role": "<role ≤45 chars>", "unit": "<unit ≤40 chars>", "dates": "<dates ≤20 chars>"}
      Look for the military entry in the MASTER PROFILE under the dedicated
      MILITARY SERVICE section. Copy role, unit, and dates verbatim from there.
      If the field already exists in cv_data, overwrite it with the canonical
      profile values — never leave military in the experience array.
  This is strictly permitted and is NOT hallucination — the data comes from
  the candidate's verified profile, not from invention.

  ANTI-HALLUCINATION — CONFIRMATION WITHOUT ACTION IS FORBIDDEN:
  If your response status is "success", your cv_data MUST contain the actual
  mutation. You MUST NOT output a conversational message such as "I have added
  the military service" or "Done, it's included now" while leaving cv_data
  unchanged. Any status="success" response where cv_data is byte-for-byte
  identical to the input is a critical error. If you cannot apply the change,
  use status="rejected" with a clear explanation instead.

"warning" — The edit is possible but significantly destructive. Do NOT apply it.
  Set cv_data to the UNCHANGED input JSON.
  Write a clear, direct message explaining the specific risk.
  Tell the user they can confirm by sending "Yes, do it anyway" or similar.

  Use "warning" when the user asks to:
  • Remove GO-OUT or the most detailed/primary experience entry
  • Delete more than half the experience entries in one instruction
  • Remove the entire skills section or education section
  • Any change that would clearly tank ATS keyword coverage

"rejected" — The edit is impossible under the system's rules. Do NOT apply it.
  Set cv_data to the UNCHANGED input JSON.
  Write a polite, specific explanation.

  Use "rejected" ONLY when the user asks to:
  • Add an employer, role, job title, metric, or tool that is NOT in the
    current cv_data AND NOT found anywhere in the MASTER PROFILE
    (e.g. "add a Google internship I never had", "invent 3 years at Amazon")
  • "Make up", "hallucinate", "fabricate", or invent content absent from
    BOTH the current CV and the Master Profile
  • Completely rewrite the entire CV — tell them to use the "Regenerate" button
  • Do something unrelated to CV editing

  DO NOT reject restore/add requests when the content exists in the Master Profile.

OVERRIDE RULE: If the user's prompt explicitly confirms a previous warning
  (e.g., "Yes, do it anyway", "I'm sure, delete it", "go ahead regardless"),
  treat the request as "success" and apply the change.

VOLUNTEERING RULE — strict default-off:
  Do NOT add, restore, or preserve the "volunteering" field in cv_data unless
  ONE of these conditions is explicitly true:
    a) The user's instruction directly requests it
       (e.g. "add volunteering", "include the Perach project").
    b) The job description (referenced in the user's prompt) explicitly
       lists mentoring, coaching, or social/community involvement as a
       core requirement — and volunteering directly satisfies it.
  In all other cases: set "volunteering" to an empty string "".
  NEVER add volunteering speculatively or as a filler to occupy sidebar space.

══════════════════════════════════════════
FORMATTING RULES (apply to any text you write or mutate)
══════════════════════════════════════════
1. NEVER use em-dash (—) or en-dash (–). Use hyphen (-) only.
2. BANNED WORDS: spearheaded, orchestrated, navigated, harnessed, leveraged,
   fostered, catalyzed, delve, testament, paramount, meticulous, transformative,
   synergy, pivotal, embark, underscore, commendable, intricate, nuanced.
3. Bullets open with a strong active verb. No passive voice.
4. No hollow adverbs: effectively, successfully, seamlessly, proactively.
5. Bullets: 60-240 characters. Grounded in what is already in the JSON or
   the Master Profile details field.
6. Do NOT invent metrics, companies, tools, or experiences that appear in
   neither the current cv_data nor the Master Profile.

══════════════════════════════════════════
OUTPUT
══════════════════════════════════════════
Return ONLY the JSON wrapper above. No markdown fences. No prose before or after.
"""


def _serialize_master_profile(master_profile: dict) -> str:
    """
    Serialize the relevant parts of USER_PROFILE for injection into the model
    context. Includes experience (with all nested roles/details), education, and
    skills so the model can locate any restorable content by name.

    Military service is serialised as a DEDICATED section separate from
    experience so the model knows to place it in the top-level "military" key
    of cv_data — never in the experience array.
    """
    parts: list[str] = []

    experience    = master_profile.get("experience", [])
    military_entries: list[dict] = []   # collected for the MILITARY section below

    if experience:
        parts.append("EXPERIENCE (civilian history; earliest first):")
        for exp in experience:
            # Military entries have a "unit" key but no "company" key.
            # Extract them into the dedicated section below instead of here.
            if exp.get("unit") and not exp.get("company"):
                military_entries.append(exp)
                continue

            company = exp.get("company", "")
            role    = exp.get("role", "")
            period  = exp.get("period", "")
            details = exp.get("details", "")
            tag     = exp.get("tag", "")

            header = f"  [{company}] {role} | {period}"
            if tag:
                header += f" [tag: {tag}]"
            parts.append(header)
            if details:
                parts.append(f"    Details: {details}")

            # GO-OUT style: nested roles list
            nested_roles = exp.get("roles", [])
            for nr in nested_roles:
                parts.append(
                    f"    Sub-role: {nr.get('title', '')} | {nr.get('period', '')}"
                )
                if nr.get("details"):
                    parts.append(f"      {nr['details']}")

    # ── Dedicated MILITARY SERVICE section ────────────────────────────────────
    # When the user asks to add/restore military service, the model MUST copy
    # these values into the TOP-LEVEL "military" key of cv_data:
    #   {"role": "...", "unit": "...", "dates": "..."}
    # Do NOT place military in the experience array.
    if military_entries:
        parts.append(
            '\nMILITARY SERVICE — inject into cv_data["military"] key (NOT experience):'
        )
        for mil in military_entries:
            role   = mil.get("role", "")
            unit   = mil.get("unit", "")
            period = mil.get("period", "")
            parts.append(
                f'  cv_data["military"] = {{"role": "{role}", "unit": "{unit}", "dates": "{period}"}}'
            )
            if mil.get("details"):
                parts.append(f"    (Context: {mil['details'][:200]})")

    education = master_profile.get("education", [])
    if education:
        parts.append("\nEDUCATION:")
        for edu in education:
            if "degree" in edu:
                parts.append(
                    f"  {edu['degree']} at {edu.get('school', '')} "
                    f"({edu.get('period', '')}) — {edu.get('status', '')}"
                )
            if "certification" in edu:
                parts.append(
                    f"  Certification: {edu['certification']} from "
                    f"{edu.get('provider', '')} — {edu.get('details', '')}"
                )

    skills = master_profile.get("skills", [])
    if skills:
        parts.append(f"\nSKILLS: {', '.join(skills)}")

    return "\n".join(parts) if parts else "(no master profile data available)"


def _sanitize_history(raw: list[dict]) -> list[dict]:
    """
    Validate and normalise a raw chat history list for the Anthropic messages API.

    Rules enforced:
    - Only "user" and "assistant" roles are kept; other roles are dropped.
    - Turns must strictly alternate, starting with "user".
      Any turn that would break alternation is dropped.
    - Empty-content turns are dropped.
    - If the last surviving turn is "user", it is removed so that the caller
      can safely append the current user message without violating alternation.
    """
    sanitized: list[dict] = []
    expected_role = "user"
    for turn in raw:
        role    = str(turn.get("role", "")).strip().lower()
        content = str(turn.get("content", "")).strip()
        if role not in ("user", "assistant") or not content:
            continue
        if role != expected_role:
            continue  # drop out-of-order turn
        sanitized.append({"role": role, "content": content})
        expected_role = "assistant" if expected_role == "user" else "user"

    # Drop a trailing "user" turn — the current user message will follow immediately
    if sanitized and sanitized[-1]["role"] == "user":
        sanitized.pop()

    return sanitized


class CopilotAgent:
    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def edit(
        self,
        cv_data: dict,
        user_prompt: str,
        master_profile: Optional[dict] = None,
        chat_history: Optional[list[dict]] = None,
    ) -> dict:
        """
        Apply (or decline) the user's editing instruction.

        master_profile should be USER_PROFILE from backend.services.user_profile.
        When provided, the agent can restore/add any experience or credential from
        the candidate's full history — not just what is already in cv_data.

        chat_history is an optional list of prior {role, content} turns.  When
        present, they are prepended to the messages array so the model understands
        conversational follow-ups like "make that bullet shorter".

        Always returns:
          {"status": "success"|"warning"|"rejected", "message": str|None, "cv_data": dict}

        Never raises on model errors — falls back to a "rejected" result so the
        caller can always forward a structured response to the frontend.
        """
        profile_section = (
            _serialize_master_profile(master_profile)
            if master_profile
            else "(master profile not provided — restore operations may be limited)"
        )

        # Current user turn always carries the full CV + master profile so the
        # model has the authoritative state even mid-conversation.
        current_user_msg = (
            f"USER INSTRUCTION:\n{user_prompt.strip()}\n\n"
            f"CURRENT CV JSON:\n"
            f"{json.dumps(cv_data, ensure_ascii=False, indent=2)}\n\n"
            f"MASTER PROFILE — VERIFIED FULL HISTORY "
            f"(use this to restore or add content the user requests):\n"
            f"{profile_section}"
        )

        # Build the messages array: validated history turns + current user message.
        # History entries are lightweight (just the user's instruction text and
        # the assistant's brief status), NOT the full cv_data, to keep tokens low.
        prior_turns = _sanitize_history(chat_history) if chat_history else []
        messages    = prior_turns + [{"role": "user", "content": current_user_msg}]

        logger.info(
            "[CopilotAgent] edit  prompt=%r  exps=%d  history_turns=%d",
            user_prompt[:80],
            len(cv_data.get("experience", [])),
            len(prior_turns),
        )

        try:
            response = await self._client.messages.create(
                model       = _MODEL,
                max_tokens  = _MAX_TOKENS,
                temperature = 0.15,
                system      = _SYSTEM_PROMPT,
                messages    = messages,
            )
        except Exception as exc:
            logger.exception("[CopilotAgent] API call failed: %s", exc)
            return {
                "status":  "rejected",
                "message": "The edit service is temporarily unavailable. Please try again.",
                "cv_data": cv_data,
            }

        raw = response.content[0].text.strip()
        original_raw = raw  # keep for fallback message

        # Strip optional markdown fences
        if raw.startswith("```json"):
            raw = raw[7:]
        elif raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]

        # ── Parse wrapper ────────────────────────────────────────────────────
        try:
            wrapper = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[CopilotAgent] Non-JSON response (falling back to rejected): %s\n"
                "--- raw (first 300) ---\n%s\n---",
                exc, original_raw[:300],
            )
            return {
                "status":  "rejected",
                "message": original_raw[:400] if original_raw.strip() else
                           "This edit cannot be performed.",
                "cv_data": cv_data,
            }

        status  = str(wrapper.get("status", "success")).lower()
        message = wrapper.get("message") or None

        # ── Non-mutating statuses: return original cv_data unchanged ─────────
        if status in ("warning", "rejected"):
            logger.info("[CopilotAgent] %s  message=%r", status, (message or "")[:80])
            return {
                "status":  status,
                "message": message or ("Request declined." if status == "rejected"
                                       else "Destructive edit detected."),
                "cv_data": cv_data,
            }

        # ── Success: extract, validate, and sanitise the mutated cv_data ─────
        inner = wrapper.get("cv_data")
        if not isinstance(inner, dict):
            logger.warning("[CopilotAgent] success status but cv_data missing or invalid")
            return {
                "status":  "rejected",
                "message": "The edit could not be applied. Please rephrase your instruction.",
                "cv_data": cv_data,
            }

        inner = _enforce_limits(inner)
        inner = _sanitize_ai_tells(inner)

        logger.info(
            "[CopilotAgent] success  exps=%d",
            len(inner.get("experience", [])),
        )
        return {
            "status":  "success",
            "message": message,
            "cv_data": inner,
        }
