"""
TruthCheckAgent — goal-oriented, multi-turn truth investigation.

The agent conducts a conversation to determine whether a candidate genuinely
has the experience a role requires.  It asks one probing question at a time and
terminates as soon as it reaches high confidence — immediately on a specific,
detailed answer, or after at most 5 questions.

Conversation contract (stateless per HTTP call)
-----------------------------------------------
The caller maintains the full conversation history and passes it on every turn.

History entry shapes:
  {role: "agent", content: <question text>, gap_addressed: <str>, raw: <raw JSON>}
  {role: "user",  content: <answer text>}

Return value (one of three shapes):
  {status: "question", question: str, gap_addressed: str, raw: str}
  {status: "verified", fit_score_adjustment: 0, cv_advice: str, summary: str, raw: str}
  {status: "failed",   fit_score_adjustment: float (-8 to -25), summary: str, raw: str}
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import List, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=True)

logger = logging.getLogger(__name__)

_MODEL      = "claude-sonnet-4-6"
_MAX_TOKENS = 1000
_MAX_QUESTIONS = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cv_summary(cv_data: dict) -> str:
    parts: list[str] = []
    name = cv_data.get("name", "")
    if name:
        parts.append(f"Candidate: {name}")
    summary = cv_data.get("professional_summary", "")
    if summary:
        parts.append(f"Summary: {str(summary)[:300]}")
    for exp in (cv_data.get("experience") or [])[:4]:
        title  = exp.get("title", "")
        company = exp.get("company", "")
        bullets = (exp.get("bullets") or [])[:3]
        if title and company:
            b = "; ".join(str(x) for x in bullets) if bullets else "—"
            parts.append(f"• {title} at {company}: {b}")
    skills = cv_data.get("skills") or []
    if skills:
        parts.append(f"Skills: {', '.join(str(s) for s in skills[:12])}")
    return "\n".join(parts) or "No experience data provided."


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        text = "\n".join(inner)
    return text.strip()


# ── Agent ─────────────────────────────────────────────────────────────────────

class TruthCheckAgent:
    """
    Stateless agent.  Caller owns history; one HTTP call = one conversation turn.
    """

    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=api_key)

    async def chat_turn(
        self,
        job_title:     str,
        company:       str,
        jd_text:       Optional[str],
        critical_gaps: List[str],
        cv_data:       dict,
        history:       List[dict],
    ) -> dict:
        """
        Process one turn and return a question or a verdict.

        history is a flat list of {role, content, [gap_addressed], [raw]} dicts
        in chronological order.  The last entry must be a user answer (or history
        can be empty for the opening question).
        """
        cv_summary   = _cv_summary(cv_data)
        gaps_text    = "\n".join(f"• {g}" for g in critical_gaps) if critical_gaps \
                       else "No pre-detected gaps — infer from job description."
        jd_excerpt   = (jd_text or "No description provided.")[:1200]
        n_asked      = sum(1 for h in history if h.get("role") == "agent")
        remaining    = _MAX_QUESTIONS - n_asked

        system = f"""You are a senior technical recruiter conducting a confidential truth-verification interview. Your ONLY goal is to determine, with high confidence, whether this candidate genuinely has the experience this role demands.

ROLE: {job_title} at {company}

JOB DESCRIPTION:
{jd_excerpt}

GAPS TO INVESTIGATE:
{gaps_text}

CANDIDATE'S STATED BACKGROUND:
{cv_summary}

INVESTIGATION STATUS: {n_asked} question(s) asked so far. {remaining} remaining (hard cap: {_MAX_QUESTIONS} total).

━━━ TERMINATION RULES (non-negotiable) ━━━
• A SPECIFIC answer with real metrics, named projects, or concrete outcomes → conclude "verified" IMMEDIATELY — do not ask follow-ups out of habit.
• A VAGUE answer ("I worked on something similar", "I have experience with...") → either probe once more OR conclude "failed" if you already have a clear picture.
• A CONTRADICTORY answer that conflicts with the stated background → conclude "failed" IMMEDIATELY.
• When remaining = 0, you MUST conclude ("verified" or "failed") — no more questions.

━━━ RESPONSE FORMAT — strict JSON only, no prose, no markdown ━━━

Asking a question:
{{"status":"question","question":"<exact question>","gap_addressed":"<which JD requirement this targets, 1 sentence>"}}

Concluding verified:
{{"status":"verified","fit_score_adjustment":0,"cv_advice":"<specific, actionable advice on phrasing this experience in the CV to raise the ATS keyword score>","summary":"<2-3 sentences explaining exactly why the candidate passed>"}}

Concluding failed:
{{"status":"failed","fit_score_adjustment":<-8 to -25 based on severity>,"summary":"<2-3 honest sentences identifying the exact gap>"}}"""

        # Build the Anthropic messages array from history
        messages: list[dict] = [
            {"role": "user", "content": "Start the investigation. Ask your first question."}
        ]
        for entry in history:
            role = entry.get("role")
            if role == "agent":
                # Use the raw JSON the agent originally produced so it sees its own phrasing
                raw = entry.get("raw") or json.dumps({
                    "status":       "question",
                    "question":     entry.get("content", ""),
                    "gap_addressed": entry.get("gap_addressed", ""),
                })
                messages.append({"role": "assistant", "content": raw})
            elif role == "user":
                messages.append({"role": "user", "content": entry.get("content", "")})

        response = self._client.messages.create(
            model      = _MODEL,
            max_tokens = _MAX_TOKENS,
            system     = system,
            messages   = messages,
        )

        raw_text = response.content[0].text
        try:
            data = json.loads(_strip_fences(raw_text))
        except json.JSONDecodeError as exc:
            logger.error("[TruthCheckAgent] JSON parse failed: %s — raw: %r", exc, raw_text[:200])
            raise ValueError(f"Agent returned unparseable JSON: {exc}") from exc

        data["raw"] = raw_text   # attach so frontend can store it for next turn
        logger.info(
            "[TruthCheckAgent] turn status=%s q_asked=%d",
            data.get("status"), n_asked + (1 if data.get("status") == "question" else 0),
        )
        return data
