import logging
import os
from typing import Optional

from dotenv import load_dotenv

from backend.utilities.ai_scrubber import clean_ai_text
from backend.services.llm_client import call_llm
from backend.services.llm_validation import harden_system_prompt, sanitize_text

# Load environment variables if needed
load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_MAX_TOKENS = 500

_GAP_SYSTEM = """You are an expert career coach and technical recruiter.
Your task is to analyze a candidate's profile against a specific job description and identify the critical skills or experiences the candidate is explicitly missing.

Rules:
1. Focus ONLY on skills or requirements explicitly requested in the job description that are NOT present in the candidate's profile.
2. Be concise and actionable. Do not provide a long introduction.
3. List the gaps clearly (e.g., using bullet points).
4. Do not invent requirements or make assumptions.
5. NO subject line or pleasantries. Output ONLY the analysis.
6. The output MUST be strictly in English."""

_GAP_USER_TMPL = """Analyze the skills gap between the candidate and the job description.

JOB DESCRIPTION:
{jd_text}

CANDIDATE PROFILE:
{candidate_material}"""


async def analyze_skills_gap(jd_text: str, user_profile: str) -> str:
    """
    Compare a user's profile against a parsed job description to identify
    explicitly missing skills or experience gaps.
    """
    if not jd_text.strip() or not user_profile.strip():
        return "Insufficient data to perform a skills gap analysis."

    user_prompt = _GAP_USER_TMPL.format(
        jd_text=sanitize_text(jd_text[:8000]),
        candidate_material=sanitize_text(user_profile[:8000]),
    )

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY is not set. Returning error message.")
        return "Error: Missing API Key"

    try:
        result = await call_llm(
            system=harden_system_prompt(_GAP_SYSTEM),
            messages=[{"role": "user", "content": user_prompt}],
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
            purpose="skills_gap_analyze",
        )

        raw_text = result.text
        # Scrubber handles generic AI tells
        return clean_ai_text(raw_text).strip()
    except Exception as e:
        logger.error("Error generating skills gap analysis: %s", e)
        return "Failed to generate skills gap analysis."
