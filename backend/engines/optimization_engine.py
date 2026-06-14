"""
CV Optimization Engine
======================
Takes a MatchAnalysis (weaknesses + red_flags) and a UserProfile and produces
an OptimizationReport: a prioritised list of before/after CV rewrites that
directly address the scoring gaps.

Design principles
-----------------
- Zero hallucination: Claude is explicitly forbidden from inventing facts.
  Unknown numbers become typed placeholders ([X%], [N users], [Feature Name]).
- Weakness-driven: only red_flags and weaknesses from the analysis are targeted —
  no generic CV advice that doesn't address the actual score blockers.
- Ownership-first rewriting: passive/participation language is transformed into
  active, first-person ownership with measurable outcomes.
- Same JSON resilience as matching_engine: two-pass parser + character-walk repair.
- Model fallback: 404 / NotFoundError triggers the next model in the list.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import anthropic
from dotenv import load_dotenv

from models.matching import MatchAnalysis
from models.optimization import CVImprovement, OptimizationReport
from models.user import UserProfile

load_dotenv(override=True)

logger = logging.getLogger(__name__)

# ── Placeholder utilities (used by both the engine and run_interview.py) ──────

# Matches any [Token] that starts with a letter, is non-empty, contains no
# nested brackets or newlines, and is at most 40 chars — covers every token
# the system prompt defines ([X%], [N], [Feature Name], [Metric], [Timeframe])
# without false-positives on markdown or JSON fragments.
import re as _re
_PLACEHOLDER_RE = _re.compile(r"\[[A-Za-z][^\[\]\n]{0,38}\]")


def extract_placeholders(text: str) -> list[str]:
    """
    Return unique placeholder tokens from *text* in order of first appearance.

    Example
    -------
    >>> extract_placeholders("Grew [Metric] by [X%] within [Timeframe], impacting [N] clients")
    ['[Metric]', '[X%]', '[Timeframe]', '[N]']
    """
    seen: dict[str, None] = {}
    for m in _PLACEHOLDER_RE.finditer(text):
        seen.setdefault(m.group(), None)
    return list(seen)


def substitute_placeholders(text: str, values: dict[str, str]) -> str:
    """
    Replace every placeholder token in *text* with its value from *values*.
    Tokens not present in *values* are left unchanged.

    Example
    -------
    >>> substitute_placeholders("Grew by [X%]", {"[X%]": "23%"})
    'Grew by 23%'
    """
    for token, value in values.items():
        text = text.replace(token, value)
    return text


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class OptimizationConfig:
    primary_model: str = "claude-sonnet-4-6"
    fallback_models: list[str] = field(default_factory=lambda: [
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    ])
    max_tokens: int = 4096


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior technical recruiter and CV writing expert who specialises in
turning Customer Success and Operations backgrounds into compelling Product Manager CVs.

You have received a forensic match analysis that identified specific weaknesses and
red flags preventing a candidate from scoring above 70/100. Your job is to rewrite
the weakest sections of their CV to directly address those blockers.

══════════════════════════════════════════════
REWRITING RULES — NON-NEGOTIABLE
══════════════════════════════════════════════

1. ZERO HALLUCINATION
   Never invent facts, companies, products, or outcomes that are not in the profile.
   If a number is missing, insert a typed placeholder — do NOT guess.

2. PLACEHOLDER FORMAT (use these exact tokens)
   [X%]          — unknown percentage improvement or change
   [N]           — unknown count (users, tickets, events, clients)
   [Feature Name]— unnamed product feature or initiative
   [Metric]      — unnamed KPI or success measure
   [Timeframe]   — unspecified time period (e.g., "within [Timeframe]")
   Placeholders must be surrounded by brackets and capitalised exactly as above.
   The candidate will replace them with real numbers before submitting.

3. OWNERSHIP LANGUAGE
   Eliminate passive and participation language. Replace with first-person
   active verbs that signal full ownership:
   BANNED → "participated in", "helped with", "assisted", "was involved in",
             "worked on a team that", "supported", "contributed to"
   REQUIRED → "Owned", "Shipped", "Defined", "Led", "Reduced", "Grew",
               "Architected", "Negotiated", "Launched", "Drove", "Scaled"

4. METRICS DENSITY
   Every bullet must answer at least one of: How much? How many? By when?
   If the original has zero numbers, add placeholders for all three.
   If the original has one number, add placeholders for the missing two.

5. SCOPE AMPLIFICATION
   Make scope explicit where it is vague:
   - "managed clients" → "managed [N] enterprise clients across [region]"
   - "worked with developers" → "led cross-functional delivery with a team of [N] engineers"
   Never overstate — use placeholders, not invented specifics.

6. SENIORITY CALIBRATION
   Rewrite language to match the target seniority level supplied in the prompt.
   APM/Junior: focus on execution and learning velocity.
   PM: focus on product ownership and measurable outcomes.
   Senior PM: focus on strategy, cross-functional leadership, and org-wide impact.

══════════════════════════════════════════════
COVERAGE REQUIREMENT
══════════════════════════════════════════════
You MUST produce at least one CVImprovement per weakness and per red_flag supplied.
If a weakness maps to multiple bullets, rewrite the most impactful one and note the
others in logic_behind_change.

══════════════════════════════════════════════
OUTPUT FORMAT
══════════════════════════════════════════════
Return ONLY raw JSON — no markdown fences, no prose outside the object.

{
  "executive_summary": "<2-3 sentences: biggest gaps found and overall rewrite strategy>",
  "priority_order": ["<label>", ...],
  "improvements": [
    {
      "original_section": "<exact original text>",
      "improved_section": "<rewritten text with placeholders>",
      "logic_behind_change": "<what was weak and which red_flag/weakness this addresses>",
      "added_metrics": ["[X%]", "[N]", ...]
    }
  ]
}

Order improvements by impact: the change most likely to raise the match score goes first.
"""


# ── JSON repair utilities (character-walk — identical to matching_engine) ─────

def _repair_truncated_json(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()

    if in_string:
        text += '"'
    stripped = text.rstrip()
    if stripped.endswith(","):
        text = stripped[:-1]
    text += "".join(reversed(stack))
    return text


def _parse_json(raw_text: str) -> dict:
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    repaired = _repair_truncated_json(text)
    try:
        result = json.loads(repaired)
        logger.warning("_parse_json: truncation repair was used — response may have been cut off")
        return result
    except json.JSONDecodeError as exc:
        logger.error(
            "_parse_json: both passes failed.\n"
            "  Error   : %s\n  Original: %.400s\n  Repaired: %.400s",
            exc, raw_text, repaired,
        )
        raise


# ── Engine ────────────────────────────────────────────────────────────────────

class OptimizationEngine:
    """
    Generates targeted CV rewrites for every weakness and red_flag found
    by the MatchingEngine, using typed placeholders instead of hallucinated facts.

    Usage
    -----
        engine = OptimizationEngine()
        report = await engine.generate_suggestions(user_profile, match_analysis)
        for item in report.improvements:
            print(item.original_section)
            print(item.improved_section)
    """

    def __init__(self, config: OptimizationConfig | None = None) -> None:
        self.config = config or OptimizationConfig()
        self._client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    # ── Model fallback ────────────────────────────────────────────────────────

    async def _call_with_fallback(self, **kwargs) -> tuple[anthropic.types.Message, str]:
        """Try models in order; return (message, model_id_used)."""
        models = [self.config.primary_model, *self.config.fallback_models]
        last_error: Exception | None = None

        for model_id in models:
            try:
                msg = await self._client.messages.create(model=model_id, **kwargs)
                if model_id != self.config.primary_model:
                    logger.warning("Primary model unavailable — used fallback: %s", model_id)
                return msg, model_id
            except anthropic.NotFoundError as exc:
                logger.warning("Model %r not found (404), trying next: %s", model_id, exc)
                last_error = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code == 404:
                    logger.warning("Model %r returned 404, trying next: %s", model_id, exc)
                    last_error = exc
                else:
                    raise

        raise last_error  # type: ignore[misc]

    # ── Core method ───────────────────────────────────────────────────────────

    async def generate_suggestions(
        self,
        user_profile: UserProfile,
        match_analysis: MatchAnalysis,
        cv_text: str = "",
        target_role: str = "",
    ) -> OptimizationReport:
        """
        Generate a prioritised OptimizationReport addressing every weakness
        and red_flag from the supplied MatchAnalysis.

        Parameters
        ----------
        user_profile   : Candidate profile (from models.user.UserProfile).
        match_analysis : Output of MatchingEngineAgent.score() — the source of
                         weaknesses and red_flags to target.
        cv_text        : Optional raw CV text. When provided, Claude can quote
                         specific lines for more precise before/after rewrites.
        target_role    : Optional role title (e.g. "Associate Product Manager at Monday.com")
                         used to calibrate seniority and domain language.
        """
        # ── Build structured gap context ──────────────────────────────────────
        weaknesses_block = "\n".join(
            f"  - {w}" for w in match_analysis.weaknesses
        ) or "  (none listed)"

        red_flags_block = "\n".join(
            f"  ! {r}" for r in match_analysis.red_flags
        ) or "  (none listed)"

        recommendations_block = "\n".join(
            f"  → {r}" for r in match_analysis.recommendations
        ) or "  (none listed)"

        profile_block = (
            f"Skills         : {', '.join(user_profile.skills) or '(none listed)'}\n"
            f"Experience     : {user_profile.years_of_experience} years\n"
            f"Seniority      : {user_profile.seniority_level}\n"
            f"Summary        : {user_profile.summary or '(none provided)'}"
        )

        cv_block = (
            f"\n── RAW CV TEXT (use for precise before/after quotes) ──\n{cv_text.strip()}"
            if cv_text.strip()
            else "\n(No raw CV text provided — base rewrites on profile summary and skills.)"
        )

        role_block = (
            f"\nTarget role: {target_role.strip()}"
            if target_role.strip()
            else ""
        )

        score_context = (
            f"Overall score  : {match_analysis.overall_score}/100\n"
            f"Skills match   : {match_analysis.breakdown.skills_match:.0f}/100\n"
            f"Exp match      : {match_analysis.breakdown.experience_match:.0f}/100\n"
            f"Domain match   : {match_analysis.breakdown.domain_match:.0f}/100\n"
            f"Seniority match: {match_analysis.breakdown.seniority_match:.0f}/100"
        )

        user_prompt = f"""\
Rewrite the candidate's weakest CV sections to directly address the scoring gaps below.{role_block}

── SCORE BREAKDOWN ──
{score_context}

── WEAKNESSES TO ADDRESS ──
{weaknesses_block}

── RED FLAGS TO ADDRESS ──
{red_flags_block}

── RECRUITER RECOMMENDATIONS (use as rewrite brief) ──
{recommendations_block}

── CANDIDATE PROFILE ──
{profile_block}
{cv_block}

Instructions:
1. Produce one CVImprovement per weakness and per red_flag (minimum).
2. Quote the original text exactly where available; write a plausible reconstruction
   where the exact text is absent (mark reconstructions with "(reconstructed)").
3. Use typed placeholders ([X%], [N], [Feature Name], [Metric], [Timeframe])
   wherever real numbers are unknown. NEVER invent specific figures.
4. Order improvements by impact on the overall score — highest first.

Return the JSON object now."""

        message, model_used = await self._call_with_fallback(
            max_tokens=self.config.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        payload = _parse_json(message.content[0].text)

        improvements = [
            CVImprovement(
                original_section=  item.get("original_section", ""),
                improved_section=  item.get("improved_section", ""),
                logic_behind_change=item.get("logic_behind_change", ""),
                added_metrics=     item.get("added_metrics", []),
            )
            for item in payload.get("improvements", [])
        ]

        report = OptimizationReport(
            executive_summary=payload.get("executive_summary", ""),
            priority_order=   payload.get("priority_order", []),
            improvements=     improvements,
            model_used=       model_used,
        )

        logger.info(
            "OptimizationReport: %d improvements, priority=%s, model=%s",
            len(report.improvements),
            report.priority_order,
            model_used,
        )
        return report
