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
_MAX_TOKENS = 600

# ---------------------------------------------------------------------------
# Prompts for Question Generation
# ---------------------------------------------------------------------------
_QUESTION_SYSTEM = """You are a tough but fair technical interviewer.
Your goal is to generate ONE targeted interview question for a candidate.
You have the job description, the candidate's profile, and the known skills gap.

Rules:
1. Ask exactly ONE question.
2. The question should probe their experience or test their theoretical understanding of a critical missing skill or a core job requirement.
3. Be direct. Do not introduce yourself or use pleasantries.
4. Output ONLY the question.
5. The output MUST be strictly in English."""

_QUESTION_USER_TMPL = """Generate a targeted interview question based on the following context.

JOB DESCRIPTION:
{jd_text}

CANDIDATE PROFILE:
{candidate_material}

KNOWN SKILLS GAP:
{skills_gap}"""

# ---------------------------------------------------------------------------
# Prompts for Answer Evaluation
# ---------------------------------------------------------------------------
_EVALUATION_SYSTEM = """You are an expert technical interviewer evaluating a candidate's answer.
Your goal is to provide constructive feedback on their response to your question.

Rules:
1. Assess the answer's accuracy, depth, and relevance to the job description.
2. Provide specific, actionable suggestions for improvement.
3. Be professional and constructive.
4. Do not use generic AI pleasantries or filler words (e.g., "I hope this helps", "As an AI").
5. The output MUST be strictly in English."""

_EVALUATION_USER_TMPL = """Evaluate the candidate's answer to the interview question in the context of the job description.

JOB DESCRIPTION:
{jd_text}

QUESTION ASKED:
{question}

CANDIDATE'S ANSWER:
{answer}"""


async def generate_interview_question(jd_text: str, user_profile: str, skills_gap: str) -> str:
    """
    Generate a contextual interview question based on the job requirements
    and the user's specific gaps.
    """
    if not jd_text.strip() or not user_profile.strip():
        return "Can you tell me about your background?"

    user_prompt = _QUESTION_USER_TMPL.format(
        jd_text=sanitize_text(jd_text[:4000]),
        candidate_material=sanitize_text(user_profile[:4000]),
        skills_gap=sanitize_text(skills_gap[:1000]),
    )

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY is not set.")
        return "API Key missing. Unable to generate question."

    try:
        result = await call_llm(
            system=harden_system_prompt(_QUESTION_SYSTEM),
            messages=[{"role": "user", "content": user_prompt}],
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.7,  # Slight variation is good for questions
            purpose="interview_generate_question",
        )

        return clean_ai_text(result.text).strip()
    except Exception as e:
        logger.error("Error generating interview question: %s", e)
        return "Failed to generate interview question."


async def evaluate_interview_answer(question: str, answer: str, jd_text: str) -> str:
    """
    Evaluate the user's provided answer, offering constructive feedback
    and suggestions for improvement.
    """
    if not question.strip() or not answer.strip():
        return "Insufficient context to evaluate the answer."

    user_prompt = _EVALUATION_USER_TMPL.format(
        jd_text=sanitize_text(jd_text[:4000]),
        question=sanitize_text(question[:500]),
        answer=sanitize_text(answer[:4000]),
    )

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY is not set.")
        return "API Key missing. Unable to evaluate answer."

    try:
        result = await call_llm(
            system=harden_system_prompt(_EVALUATION_SYSTEM),
            messages=[{"role": "user", "content": user_prompt}],
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.0,  # Deterministic for evaluation
            purpose="interview_evaluate_answer",
        )

        return clean_ai_text(result.text).strip()
    except Exception as e:
        logger.error("Error evaluating interview answer: %s", e)
        return "Failed to evaluate interview answer."
