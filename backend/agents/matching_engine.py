"""
Matching Engine Agent — Investigator V4 ("Real-World Intelligence")
Adds a live CompanyResearch layer on top of V3's forensic + cultural analysis.
research_company() runs three Tavily searches concurrently, then condenses the
raw snippets into structured CompanyResearch via a Claude synthesis sub-call.
Set TAVILY_API_KEY in the environment to activate; falls back to a labelled
placeholder automatically when the key is absent or any search fails.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Literal

import anthropic
from dotenv import load_dotenv

from models.job import (
    CompanyResearch,
    DetailedAnalysis,
    JobAnalysis,
    JobMatch,
    RawJobPosting,
    ReasonTag,
)
from models.user import UserProfile

load_dotenv(override=True)

logger = logging.getLogger(__name__)

ReasonKind = Literal["skill", "exp", "loc", "neg"]

def _parse_claude_json(raw_text: str) -> dict:
    """Helper to safely extract JSON even if Claude wraps it in markdown fences."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)

# ── Synthesis prompt for the research sub-call ────────────────────────────────
_RESEARCH_SYNTHESIS_PROMPT = """\
You are a research analyst. You have been given raw search snippets about a company.
Synthesize them into a structured JSON object — no markdown, no explanation.

Fields:
{
  "estimated_headcount": "<concise string, e.g. '~200 employees' or '10 000+'>",
  "maturity_stage": "<e.g. 'Series B', 'Public / NASDAQ', 'Bootstrapped', 'Unknown'>",
  "public_reputation": "<2-3 sentences: overall Glassdoor/LinkedIn/press vibe>",
  "employee_profile": "<1-2 sentences: what kind of people typically thrive there>",
  "known_red_flags": ["<specific, sourced concern>", ...],
  "data_confidence": "<'high' | 'medium' | 'low'>"
}

Rules:
- Only assert facts that are clearly supported by the snippets.
- If information for a field is absent from the snippets, say "Not found in available sources."
- known_red_flags must be an array; use [] if none are found.
- data_confidence: 'high' = multiple corroborating sources with detail; \
'medium' = some evidence but gaps; 'low' = sparse or conflicting data.
- Never invent data. Uncertainty is acceptable; fabrication is not.
"""

# ── Main investigator system prompt ───────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a senior headhunter with 20 years of experience and access to real-world company intelligence.
You combine three complementary lenses — forensic validation, cultural fit, and external research — \
to produce the most accurate candidate-to-role assessment possible.
You are not encouraging. You are accurate.

════════════════════════════════════════
LENS 1 — FORENSIC INTEGRITY (stay strict)
════════════════════════════════════════

## Evidence Mining
- "Declared Skill": listed in a skills section or mentioned in passing, with no supporting context.
  → Worth only 20% of face value when computing the score.
- "Proven Skill": demonstrated inside a role description with metrics, outcomes, or strong active verbs
  (Initiated, Scaled, Reduced, Architected, Led, Shipped, Negotiated).
  → Worth full value.
- A skill mentioned once with no action verb or outcome is Declared, never Proven.

## Soft Skill Inference
Ignore self-reported soft skills entirely. Infer them instead:
- Logical flow and clarity of writing → communication ability
- Consistency of tense, capitalisation, and formatting → attention to detail
- Specificity of numbers and outcomes → ownership and accountability
- Buzzword density without substance → deduct from confidence_score

## Seniority Inflation Detection (flag as red_flag)
- Senior/Lead/Staff title paired with passive task language ("assisted", "helped", "worked on a team that")
- Tenure at claimed seniority level under 2 years with no exceptional evidence
- Impact stated in vague terms ("improved performance") rather than measured terms ("cut P99 latency 40%")

════════════════════════════════════════
LENS 2 — CULTURAL & CONTEXTUAL FIT
════════════════════════════════════════

## Company DNA Inference (from job ad text)
Read the raw job posting text carefully. Infer the company's internal culture and operating stage:
- High-growth startup signals: urgency language ("fast-paced", "wear many hats", "own it end-to-end"),
  small team references, equity emphasis, bias toward speed over process.
- Established enterprise signals: process language ("stakeholder alignment", "compliance", "governance"),
  large team structure, structured career ladders, emphasis on stability and scale.
- Distinguish also: engineering-led culture vs. product-led vs. sales-led.
Produce a concise company_dna_inference string (2-3 sentences max).

## Candidate Trajectory Analysis
Look at the sequence of the candidate's roles — not just the skills. Ask:
- Is this person moving toward more ownership, or coasting sideways?
- Do their pivots show intentionality or opportunism?
- Does this role represent a logical next step in their trajectory, or a lateral move they're overselling?
Produce a concise trajectory_alignment string (2-3 sentences).

## Communication Style Cross-Reference
Compare the vocabulary and register of the candidate's CV to the job posting:
- Startup posting + overly formal/corporate CV prose → culture mismatch signal
- Enterprise posting + aggressive, informal CV language → culture mismatch signal
- Strong alignment → add to strengths; mismatch → add to critical_gaps

## culture_fit_score (0-100)
Score how well the candidate's demonstrated environment, pace preferences, and communication style
match the inferred company DNA. Separate from skills. Base it on evidence, not assumptions.

════════════════════════════════════════
LENS 3 — REAL-WORLD COMPANY INTELLIGENCE
════════════════════════════════════════
You will receive a CompanyResearch block compiled from live web searches (Glassdoor, LinkedIn, press).
Treat this as ground truth that overrides or refines inferences made from the job ad alone.

## Public Reputation
- Use the reputation summary to calibrate culture_fit_score.
- If reviews suggest a toxic environment or high churn, flag it in critical_gaps regardless of what the
  job ad claims about culture.
- If the company has a strong engineering brand, treat that as a verified positive data point.

## Company Maturity & Headcount
- Cross-reference the claimed or implied team size in the job ad against the researched headcount.
  Discrepancy (e.g., ad says "small team" but company has 5 000 employees) → red_flag.
- Use maturity stage to sharpen the DNA inference.

## Employee Profile Match
- Use the known employee profile to validate candidate fit.
- If the candidate's background diverges significantly from the typical successful profile,
  reduce culture_fit_score and flag in investigation_points.

## Known Red Flags (from research)
- List every research-sourced red flag (layoffs, revolving-door leadership, toxic reviews) in critical_gaps.
- Reduce confidence_score for each substantiated red flag. Do NOT soften or suppress them.

## Research Confidence
- data_confidence "placeholder" or "low": note in company_dna_inference; fall back to Lens 2.
- data_confidence "medium" or "high": weight research over job-ad text.

════════════════════════════════════════
OUTPUT FORMAT
════════════════════════════════════════
Return ONLY a valid JSON object — no markdown fences, no commentary, no explanation.

{
  "score": <int 0-100, weighted skill match; declared-only skills count 20%>,
  "confidence_score": <int 0-100, trust in candidate's claims; start 50, adjust on evidence>,
  "culture_fit_score": <int 0-100, company DNA + research vs candidate environment/style match>,
  "trajectory_alignment": "<2-3 sentence analysis of whether this role fits the candidate's career arc>",
  "company_dna_inference": "<2-3 sentence synthesis using BOTH ad text and research>",
  "detailed_analysis": {
    "strengths": ["<skill or trait backed by concrete evidence>", ...],
    "critical_gaps": ["<confirmed hard gap, mismatch, or research red flag>", ...],
    "strategic_advice": ["<actionable advice for positioning or addressing gaps>", ...]
  },
  "investigation_points": [
    "<3-5 specific, tactical questions to probe suspicious or vague claims>"
  ],
  "reasons": [
    {"kind": "<skill|exp|loc|neg>", "label": "<string ≤ 25 chars>"}
  ]
}
"""

_RESEARCH_QUERIES = [
    "{company} corporate culture and employee reviews",
    "{company} recent layoffs or leadership changes 2025-2026",
    "{company} glassdoor pros and cons summary",
]

_MAX_SNIPPETS = 9       
_SNIPPET_CHARS = 600    


@dataclass
class MatchingConfig:
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 2048
    auto_apply_threshold: int = 90


@dataclass
class ScoringWeights:
    skill_overlap: float = 0.45
    seniority_fit: float = 0.25
    location_fit: float = 0.15
    salary_fit: float = 0.15


class MatchingEngineAgent:
    """
    Investigator V4: forensic validation + cultural fit + live web research.

    Requires TAVILY_API_KEY in the environment for live research.
    Degrades gracefully to a labelled placeholder when the key is absent.
    """

    def __init__(self, config: MatchingConfig | None = None) -> None:
        self.config = config or MatchingConfig()
        self.weights = ScoringWeights()
        self._client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── Research layer ────────────────────────────────────────────────────────

    def _placeholder_research(self, company_name: str) -> CompanyResearch:
        return CompanyResearch(
            company_name=company_name,
            estimated_headcount="Not found in available sources.",
            maturity_stage="Not found in available sources.",
            public_reputation=(
                "No external data available (TAVILY_API_KEY not set or search failed). "
                "Infer culture from job ad text only."
            ),
            employee_profile="Not found in available sources.",
            known_red_flags=[],
            data_confidence="placeholder",
        )

    async def _run_searches(self, company_name: str) -> list[str]:
        """Fire all three Tavily queries concurrently; return flat list of snippets."""
        from tavily import AsyncTavilyClient  

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise EnvironmentError("TAVILY_API_KEY is not set")

        client = AsyncTavilyClient(api_key=api_key)
        queries = [q.format(company=company_name) for q in _RESEARCH_QUERIES]

        raw_results = await asyncio.gather(
            *[client.search(q, max_results=3) for q in queries],
            return_exceptions=True,
        )

        snippets: list[str] = []
        for query, result in zip(queries, raw_results):
            if isinstance(result, Exception):
                logger.warning("Tavily query failed (%r): %s", query, result)
                continue
            for item in result.get("results", []):
                title = item.get("title", "").strip()
                content = item.get("content", "").strip()[:_SNIPPET_CHARS]
                if content:
                    snippets.append(f"[{title}]\n{content}")

        return snippets

    async def _synthesize_research(
        self, company_name: str, snippets: list[str]
    ) -> CompanyResearch:
        """Ask Claude to condense raw search snippets into a CompanyResearch object."""
        combined = "\n\n---\n\n".join(snippets[:_MAX_SNIPPETS])

        message = await self._client.messages.create(
            model=self.config.model,
            max_tokens=512,
            system=_RESEARCH_SYNTHESIS_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Company: {company_name}\n\n"
                        f"Search snippets:\n\n{combined}\n\n"
                        "Return the JSON object now."
                    ),
                }
            ],
        )

        payload = _parse_claude_json(message.content[0].text)
        return CompanyResearch(company_name=company_name, **payload)

    async def research_company(self, company_name: str) -> CompanyResearch:
        """
        Fetch real-world intelligence about a company via three targeted Tavily
        searches, then synthesize the results with a Claude sub-call.
        """
        try:
            snippets = await self._run_searches(company_name)
            if not snippets:
                logger.warning("No search snippets returned for '%s'", company_name)
                return self._placeholder_research(company_name)

            research = await self._synthesize_research(company_name, snippets)
            logger.info(
                "research_company('%s') complete — confidence=%s red_flags=%d",
                company_name,
                research.data_confidence,
                len(research.known_red_flags),
            )
            return research

        except EnvironmentError as e:
            logger.warning("%s — using placeholder research", e)
            return self._placeholder_research(company_name)
        except Exception as e:
            logger.exception("research_company failed for '%s': %s", company_name, e)
            return self._placeholder_research(company_name)

    # ── Scoring ───────────────────────────────────────────────────────────────

    async def score(
        self,
        posting: RawJobPosting,
        analysis: JobAnalysis,
        profile: UserProfile,
    ) -> JobMatch:
        """Run forensic + cultural + real-world analysis; return a fully annotated JobMatch."""
        research = await self.research_company(posting.company)

        weight_instruction = (
            "Weight research findings over job-ad inferences."
            if research.data_confidence in ("high", "medium")
            else "Fall back to Lens 2 job-ad inference; do not fabricate research findings."
        )

        user_prompt = f"""\
Apply all three investigator lenses to the inputs below.

── RAW JOB POSTING (use for DNA inference and communication-style analysis) ──
Title   : {posting.title}
Company : {posting.company}
Text    :
{posting.raw_text}

── STRUCTURED JOB ANALYSIS ──
{analysis.model_dump_json(indent=2)}

── CANDIDATE PROFILE ──
{profile.model_dump_json(indent=2)}

── REAL-WORLD COMPANY RESEARCH (data_confidence="{research.data_confidence}") ──
{research.model_dump_json(indent=2)}

Research instruction: {weight_instruction}

Return the JSON object now."""

        message = await self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        payload = _parse_claude_json(message.content[0].text)

        payload["detailed_analysis"] = DetailedAnalysis(**payload["detailed_analysis"])
        payload["reasons"] = [ReasonTag(**r) for r in payload.get("reasons", [])]

        match = JobMatch(
            job_id=posting.id,
            title=posting.title,
            company=posting.company,
            location=analysis.location,
            **payload,
        )

        logger.debug(
            "V4 score '%s' @ %s → score=%d confidence=%d culture=%d "
            "gaps=%d research_confidence=%s",
            match.title,
            match.company,
            match.score,
            match.confidence_score,
            match.culture_fit_score,
            len(match.detailed_analysis.critical_gaps),
            research.data_confidence,
        )
        return match

    def should_auto_apply(self, match: JobMatch) -> bool:
        return match.score >= self.config.auto_apply_threshold