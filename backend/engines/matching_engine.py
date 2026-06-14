"""
Matching Engine — Robust Investigator V4.1
==========================================
Combines hard-metric pre-screening (years gap, skills hit-rate, ownership
signals) with a forensic Claude analysis to produce a calibrated MatchAnalysis.

Key guarantees
--------------
- Model resilience: tries models in order; falls back on 404 / NotFoundError.
- JSON resilience: two-pass parser with character-walk truncation repair.
- Hard-metric anchoring: objective figures are pre-computed and injected into
  the prompt so Claude cannot ignore year gaps or missing skills.
- Entity extraction: ownership signals (shipped / launched / built …) are
  detected before the LLM call and flagged explicitly when absent.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

import anthropic
from dotenv import load_dotenv

from models.job import JobAnalysis, RawJobPosting
from models.matching import MatchAnalysis, ScoringBreakdown
from models.user import UserProfile

load_dotenv(override=True)

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class EngineConfig:
    """
    Centralised model and tuning config.

    primary_model     : tried first on every call.
    fallback_models   : tried in order when a 404 / NotFoundError occurs.
    max_tokens        : generous ceiling; analysis + reasoning can be long.
    score_weights     : must sum to 1.0 — used to validate Claude's overall_score.
    """
    primary_model: str = "claude-sonnet-4-6"
    fallback_models: list[str] = field(default_factory=lambda: [
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    ])
    max_tokens: int = 4096
    score_weights: dict[str, float] = field(default_factory=lambda: {
        "skills_match":     0.35,
        "experience_match": 0.30,
        "domain_match":     0.20,
        "seniority_match":  0.15,
    })


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a forensic talent evaluator with 20 years of recruiting experience in B2B SaaS.
You are NOT encouraging. You are accurate. Your purpose is to surface the truth about
candidate–role fit so the candidate can make informed decisions and improve.

══════════════════════════════════════════════
SCORING DIMENSIONS  (return all as floats 0-100)
══════════════════════════════════════════════

1. SKILLS MATCH (weight 35 %)
   • Compare required_skills and nice_to_have_skills to the candidate's skills list.
   • Required skill present in profile → full credit.
   • Nice-to-have skill present → 50 % credit.
   • Skill only in a vague summary line, no context → 20 % credit (declared, not proven).
   • Hard technical gap in required skills → heavy penalty + add to weaknesses.

2. EXPERIENCE MATCH (weight 30 %)
   You will receive pre-computed hard metrics (years_required, years_available,
   experience_gap). Use these numbers — do NOT re-estimate them.
   Penalty scale for experience_gap (job requirement minus candidate years):
     Gap = 0      → no penalty
     Gap = 1 yr   → −10 pts
     Gap = 2 yrs  → −25 pts
     Gap ≥ 3 yrs  → −40 pts + mandatory red_flag

   ⚠ FUNCTION SPECIFICITY RULE ⚠
   "Total years of experience" ≠ "PM experience." If the role requires PM-specific
   years, assess only years in a titled PM role at full credit, or years with clear
   functional PM evidence (writing specs, owning a roadmap, running sprints with
   engineering) at 60 % credit. CS / Operations titles do not count at full value
   even if they had product-adjacent responsibilities.

3. DOMAIN MATCH (weight 20 %)
   • B2B SaaS candidate → B2B SaaS role: strong positive.
   • Consumer-only background → enterprise B2B role: flag as potential mismatch.
   • Assess customer-segment familiarity: has the candidate worked with similar
     buyer personas (SMB, mid-market, enterprise, event organizers, etc.)?

4. SENIORITY MATCH (weight 15 %)
   Seniority bands (use these, do not invent your own):
     APM / Junior PM : 0-2 yrs, limited autonomy expected, coaching environment.
     PM              : 2-5 yrs, owns a product area, demonstrated shipping history.
     Senior PM       : 5+ yrs, cross-functional leadership, strategy input, mentoring.
     Staff / Principal: 8+ yrs, org-wide influence, multi-team coordination.
   Flag "Seniority Inflation" if the claimed title or implied level exceeds the
   demonstrated responsibilities or years.

══════════════════════════════════════════════
ENTITY EXTRACTION — PRODUCT OWNERSHIP SIGNALS
══════════════════════════════════════════════
You will receive a pre-computed flag: has_ownership_evidence.
If False, and the candidate is applying for a PM / Product Owner role:
→ Add "Low Product Ownership Evidence: no shipped features, product names, or
  measurable outcomes found in profile" to red_flags.

Even when the flag is True, verify quality:
• "Helped ship feature X" is weaker than "Shipped feature X that increased Y by Z %."
• Specific product names + measurable outcomes → strong ownership signal.
• Vague verbs ("involved in", "assisted with", "supported") → ownership is declared, not proven.

══════════════════════════════════════════════
HIGH-GROWTH / HIGH-BURNOUT ALIGNMENT CHECK
══════════════════════════════════════════════
For roles at high-growth B2B SaaS companies (indicators: "fast-paced", "high-growth",
"Series B/C+", "startup", "scale", "own it end-to-end"):

Positive signals (raise domain_match or add to strengths):
  • Demonstrated comfort with ambiguity and changing priorities.
  • History of rapid promotions (indicates high performer in fast-moving environments).
  • Simultaneously held multiple high-stakes responsibilities (resilience evidence).
  • Incident-management / on-call / live-ops experience under pressure.

Concern signals (add to weaknesses or red_flags):
  • Background is exclusively process-heavy, bureaucratic, or compliance-driven.
  • No evidence of self-directed work or autonomous decision-making.
  • Candidate appears to rely on structured frameworks rather than first principles.

METRICS-DRIVEN MINDSET:
  • Does the candidate cite numbers, percentages, KPIs, or measurable outcomes?
  • Absence of any metrics across the entire profile → flag in weaknesses.
  • Presence of multiple specific metrics → add to strengths.

══════════════════════════════════════════════
OUTPUT FORMAT
══════════════════════════════════════════════
Return ONLY raw JSON. No markdown fences, no prose, no explanation outside the JSON.

{
  "overall_score": <int 0-100>,
  "breakdown": {
    "skills_match":     <float 0-100>,
    "experience_match": <float 0-100>,
    "domain_match":     <float 0-100>,
    "seniority_match":  <float 0-100>
  },
  "strengths":        ["<evidence-backed strength>", ...],
  "weaknesses":       ["<evidence-backed weakness>", ...],
  "red_flags":        ["<critical concern>", ...],
  "recommendations":  ["<specific actionable step>", ...],
  "reasoning": "<One dense paragraph explaining the overall assessment and its key drivers>"
}
"""


# ── JSON repair utilities ─────────────────────────────────────────────────────

def _repair_truncated_json(text: str) -> str:
    """
    Character-walk repair for truncated JSON.
    Tracks bracket/brace depth (skipping string contents correctly),
    closes any open string, strips a trailing comma, then closes all
    unclosed containers in reverse-open order.
    """
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
    """
    Two-pass JSON extractor.

    Pass 1: strip markdown fences if present, then json.loads().
    Pass 2: run truncation repair, then json.loads().
    Raises json.JSONDecodeError only if both passes fail (always logs first).
    """
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
        logger.warning("_parse_json: truncation repair was needed — response may be cut off")
        return result
    except json.JSONDecodeError as exc:
        logger.error(
            "_parse_json: both passes failed.\n"
            "  Error   : %s\n  Original: %.400s\n  Repaired: %.400s",
            exc, raw_text, repaired,
        )
        raise


# ── Pre-screen helpers ────────────────────────────────────────────────────────

_YEARS_PATTERNS = [
    r"(\d+)\+?\s*years?\s+(?:of\s+)?(?:experience|exp)",
    r"(?:minimum|at\s+least|min\.?)\s+(\d+)\s+years?",
    r"(\d+)\s*[-–]\s*\d+\s+years?\s+(?:of\s+)?experience",
]

_OWNERSHIP_VERBS = frozenset([
    "shipped", "launched", "built", "delivered", "defined",
    "designed", "owned", "led", "created", "released", "drove",
])


def _extract_years_required(text: str) -> int | None:
    for pattern in _YEARS_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _prescreen(
    posting: RawJobPosting,
    analysis: JobAnalysis,
    profile: UserProfile,
) -> dict:
    """
    Compute objective metrics before the LLM call so Claude has hard numbers
    to anchor on — not just prose to interpret charitably.
    """
    combined_text = f"{posting.raw_text} {analysis.summary}"
    years_required = _extract_years_required(combined_text) or 0
    years_available = profile.years_of_experience
    experience_gap = max(0, years_required - years_available)

    profile_skills_lower = [s.lower() for s in profile.skills]

    def _skill_match(job_skill: str) -> bool:
        js = job_skill.lower()
        return any(js in ps or ps in js for ps in profile_skills_lower)

    matched_required = [s for s in analysis.required_skills if _skill_match(s)]
    missing_required = [s for s in analysis.required_skills if not _skill_match(s)]
    matched_nice     = [s for s in analysis.nice_to_have_skills if _skill_match(s)]

    skills_denom = max(len(analysis.required_skills), 1)
    skills_hit_rate = len(matched_required) / skills_denom * 100

    summary_lower = (profile.summary or "").lower()
    ownership_found = [v for v in _OWNERSHIP_VERBS if v in summary_lower]

    return {
        "years_required":           years_required,
        "years_available":          years_available,
        "experience_gap":           experience_gap,
        "skills_hit_rate_pct":      round(skills_hit_rate, 1),
        "required_skills_matched":  matched_required,
        "required_skills_missing":  missing_required,
        "nice_to_have_matched":     matched_nice,
        "ownership_signals_found":  ownership_found,
        "has_ownership_evidence":   bool(ownership_found),
    }


# ── Agent ─────────────────────────────────────────────────────────────────────

class MatchingEngineAgent:
    """
    Robust forensic matching engine with automatic model fallback and
    two-pass JSON repair.

    Usage
    -----
        engine   = MatchingEngineAgent()
        analysis = await engine.score(posting, job_analysis, user_profile)
        print(analysis.overall_score, analysis.red_flags)
    """

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self._client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    # ── Model resilience ──────────────────────────────────────────────────────

    async def _call_with_fallback(self, **kwargs) -> tuple[anthropic.types.Message, str]:
        """
        Try models in priority order. Returns (message, model_id_used).
        Raises the last error if all models fail.
        """
        models = [self.config.primary_model, *self.config.fallback_models]
        last_error: Exception | None = None

        for model_id in models:
            try:
                msg = await self._client.messages.create(model=model_id, **kwargs)
                if model_id != self.config.primary_model:
                    logger.warning(
                        "Primary model unavailable — used fallback: %s", model_id
                    )
                return msg, model_id
            except anthropic.NotFoundError as exc:
                logger.warning(
                    "Model %r not found (404), trying next. Detail: %s", model_id, exc
                )
                last_error = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code == 404:
                    logger.warning(
                        "Model %r returned 404, trying next. Detail: %s", model_id, exc
                    )
                    last_error = exc
                else:
                    raise  # non-404 API errors bubble up immediately

        raise last_error  # type: ignore[misc]

    # ── Score ─────────────────────────────────────────────────────────────────

    async def score(
        self,
        posting: RawJobPosting,
        analysis: JobAnalysis,
        profile: UserProfile,
        extra_context: str = "",
    ) -> MatchAnalysis:
        """
        Run pre-screening + forensic Claude analysis.

        Parameters
        ----------
        posting       : Raw job posting (title, company, full text).
        analysis      : Structured extraction from the posting.
        profile       : Candidate's UserProfile (from models.user).
        extra_context : Optional additional narrative (e.g. chat context,
                        rich USER_PROFILE text) injected verbatim.
        """
        pre = _prescreen(posting, analysis, profile)

        logger.debug(
            "Pre-screen for '%s' @ %s — gap=%d yrs, skills_hit=%.0f%%, ownership=%s",
            posting.title, posting.company,
            pre["experience_gap"],
            pre["skills_hit_rate_pct"],
            pre["ownership_signals_found"],
        )

        extra_block = (
            f"\n── ADDITIONAL CANDIDATE CONTEXT ──\n{extra_context.strip()}"
            if extra_context.strip()
            else ""
        )

        user_prompt = f"""\
Perform a forensic candidate assessment using all lenses in your instructions.

── JOB POSTING ──
Title   : {posting.title}
Company : {posting.company}
Text    :
{posting.raw_text}

── STRUCTURED JOB ANALYSIS ──
Required skills  : {analysis.required_skills}
Nice-to-have     : {analysis.nice_to_have_skills}
Seniority level  : {analysis.seniority_level}
Remote           : {analysis.is_remote}
Location         : {analysis.location}
Summary          : {analysis.summary}

── CANDIDATE PROFILE ──
Skills             : {profile.skills}
Years of experience: {profile.years_of_experience}
Seniority level    : {profile.seniority_level}
Open to remote     : {profile.open_to_remote}
Preferred locations: {profile.preferred_locations}
Summary            : {profile.summary or "(none provided)"}
{extra_block}

── PRE-COMPUTED HARD METRICS (treat as ground truth) ──
years_required          : {pre["years_required"]} (extracted from job text; 0 = not stated)
years_available         : {pre["years_available"]}
experience_gap          : {pre["experience_gap"]} years short of requirement
skills_hit_rate_pct     : {pre["skills_hit_rate_pct"]} % of required skills matched
required_skills_matched : {pre["required_skills_matched"]}
required_skills_missing : {pre["required_skills_missing"]}
nice_to_have_matched    : {pre["nice_to_have_matched"]}
has_ownership_evidence  : {pre["has_ownership_evidence"]}
ownership_signals_found : {pre["ownership_signals_found"]}

Return the JSON object now."""

        message, model_used = await self._call_with_fallback(
            max_tokens=self.config.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        payload = _parse_json(message.content[0].text)

        # Validate and clamp all numeric values defensively
        breakdown = ScoringBreakdown(
            skills_match=     float(max(0, min(100, payload["breakdown"]["skills_match"]))),
            experience_match= float(max(0, min(100, payload["breakdown"]["experience_match"]))),
            domain_match=     float(max(0, min(100, payload["breakdown"]["domain_match"]))),
            seniority_match=  float(max(0, min(100, payload["breakdown"]["seniority_match"]))),
        )

        # Sanity-check: if Claude's overall_score diverges from the weighted
        # average by more than 10 points, recompute it and log a warning.
        reported_score = int(max(0, min(100, payload["overall_score"])))
        computed_score = int(round(breakdown.weighted_average))
        if abs(reported_score - computed_score) > 10:
            logger.warning(
                "overall_score divergence: Claude reported %d, weighted average is %d — "
                "using weighted average.",
                reported_score, computed_score,
            )
            reported_score = computed_score

        result = MatchAnalysis(
            overall_score=    reported_score,
            breakdown=        breakdown,
            strengths=        payload.get("strengths", []),
            weaknesses=       payload.get("weaknesses", []),
            red_flags=        payload.get("red_flags", []),
            recommendations=  payload.get("recommendations", []),
            reasoning=        payload.get("reasoning", ""),
            model_used=       model_used,
        )

        logger.info(
            "MatchAnalysis '%s' @ %s — score=%d (skills=%.0f exp=%.0f domain=%.0f senior=%.0f) "
            "red_flags=%d model=%s",
            posting.title, posting.company,
            result.overall_score,
            breakdown.skills_match, breakdown.experience_match,
            breakdown.domain_match, breakdown.seniority_match,
            len(result.red_flags),
            model_used,
        )
        return result
