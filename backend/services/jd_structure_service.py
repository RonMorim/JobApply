"""
JD Structure Service — passes raw job description text through an LLM to produce
a clean, standardised JSON structure.

The output schema:
  {
    "company_name":    string,         # Real hiring company extracted from the JD text
    "company_details":  string,        # About the company / team context
    "role_overview":    string,        # What the role is and why it exists
    "responsibilities": [string, ...], # Key duties and accountabilities
    "requirements":     [string, ...], # Must-have skills / experience
    "advantages":       [string, ...], # Nice-to-have / preferred qualifications
    "additional_info":  string         # Compensation, benefits, process notes
  }

Fields that are genuinely absent from the source text are set to "" or [].
The result is stored in jobs.jd_structured as a JSON string.

`company_name` is also used by callers to overwrite the job.company field when
the scraper incorrectly populated it with the source platform name (e.g. "LinkedIn").
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"

# ── Pydantic output schema ────────────────────────────────────────────────────

class StructuredJd(BaseModel):
    """Strict schema for the LLM-produced structured job description."""
    company_name:     str        = ""  # real hiring company extracted from JD text
    company_details:  str        = ""
    role_overview:    str        = ""
    responsibilities: List[str]  = []
    requirements:     List[str]  = []
    advantages:       List[str]  = []
    additional_info:  str        = ""

    @field_validator("responsibilities", "requirements", "advantages", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list:
        """Accept None or a bare string; normalise to a list."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v  # type: ignore[return-value]


# ── LLM prompt ────────────────────────────────────────────────────────────────
# One attempt only.  The schema is embedded verbatim so the LLM has zero
# ambiguity.  If the output fails Pydantic validation we log once and return
# None (→ status='failed'); no retry loop.

_SYSTEM_PROMPT = """\
You are a job-description parser. Given raw job posting text, extract and
restructure the content into a strict JSON object matching EXACTLY this schema:

{
  "company_name":    "<string — the REAL hiring company's name as stated in the JD; NOT the job board or platform name (e.g. NOT 'LinkedIn', 'Indeed', 'Glassdoor')>",
  "company_details":  "<string — concise paragraph about the company/team/product context>",
  "role_overview":    "<string — what the role is, its purpose, where it sits in the org>",
  "responsibilities": ["<string>", ...],
  "requirements":     ["<string>", ...],
  "advantages":       ["<string>", ...],
  "additional_info":  "<string — salary, benefits, location, process notes>"
}

STRICT RULES — violation causes the output to be DISCARDED:
1. Output ONLY the JSON object. No markdown fences, no commentary, no preamble.
2. Start with { and end with }. Nothing before or after.
3. All seven keys must be present. Use "" for absent strings, [] for absent arrays.
4. Each bullet string must be ≤ 120 characters. Do not duplicate across arrays.
5. Write in English even if the source text is in another language (preserve names/brands).
6. For company_name: extract it from the JD body text (e.g. "monday.com", "Wolt", "Fiverr").
   If the company name is genuinely absent from the text, return "".
   NEVER return a job-board or aggregator name (LinkedIn, Indeed, Glassdoor, etc.).
"""


def _build_client():
    import anthropic
    return anthropic.Anthropic()


def _strip_fences(text: str) -> str:
    """Strip markdown code-fence wrappers the LLM may add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return text


def _parse_and_validate(raw: str) -> Optional[StructuredJd]:
    """
    Deserialise *raw* into a StructuredJd Pydantic model.

    Returns the validated model on success, or None on any failure.
    Logs the exact reason once — no retry, no silent swallow.
    """
    cleaned = _strip_fences(raw)

    # Recover the outermost JSON object if the model wrapped it in text.
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end   = cleaned.rfind("}")
        if start != -1 and end != -1:
            cleaned = cleaned[start:end + 1]
        else:
            logger.error(
                "[jd_structure] LLM output contains no JSON object — "
                "schema validation FAILED. Raw output (first 300 chars): %s",
                raw[:300],
            )
            return None

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error(
            "[jd_structure] JSON parse FAILED (%s). "
            "Raw output (first 300 chars): %s",
            exc, raw[:300],
        )
        return None

    try:
        return StructuredJd.model_validate(data)
    except ValidationError as exc:
        logger.error(
            "[jd_structure] Pydantic schema validation FAILED — %s. "
            "Parsed dict keys: %s",
            exc, list(data.keys()) if isinstance(data, dict) else type(data),
        )
        return None


# ── Nuclear JD cleaning constants ─────────────────────────────────────────────
# Section-header anchors that mark the start of the *real* job description.
# Everything before the first match is site chrome / sidebar noise.
_JD_START_HEADERS: tuple[str, ...] = (
    "about the role", "about this role", "about the job", "about the position",
    "the role", "your role", "role overview", "role summary",
    "job description", "the position", "position overview", "position summary",
    "responsibilities", "key responsibilities",
    "what you'll do", "what you will do", "what you’ll do",
    "requirements", "qualifications", "who we are", "who you are",
    "what we're looking for", "what we are looking for", "what we’re looking for",
    "overview", "job summary",
)

# Closing / CTA anchors that mark the end of the job description.  Everything
# from the first match onward is application boilerplate or "more jobs" noise.
_JD_END_MARKERS: tuple[str, ...] = (
    "interested?", "how to apply", "our process", "our hiring process",
    "recruitment process", "hiring process", "application process",
    "contact us", "get in touch", "equal opportunity employer",
    "equal employment opportunity", "we are an equal opportunity",
    "similar jobs", "related jobs", "people also viewed", "more jobs like this",
    "you may also like", "recommended jobs", "terminal x",
)

# Standalone lines that are pure site noise (nav links, social, footer, sidebar).
_NOISE_LINE_RE = re.compile(
    r"^\s*("
    r"terminal\s*x|"
    r"similar jobs|related jobs|recommended jobs|more jobs|people also viewed|"
    r"home|jobs|companies|salaries|sign in|sign up|log ?in|register|"
    r"follow us|share|tweet|facebook|linkedin|instagram|whatsapp|telegram|"
    r"©.*|all rights reserved|cookie.*|privacy.*|terms.*|"
    r"back to (search|results|jobs)|view all jobs|see all jobs"
    r")\s*$",
    re.I,
)


def _clean_raw_jd(text: str) -> str:
    """
    Aggressive ("nuclear") isolation of the real job-description body from
    surrounding site chrome, sidebars, and footers, run before _preprocess_jd().

    Three passes:
      1. Header lock-on — drop everything before the first recognised JD section
         header (About the role / Responsibilities / Requirements / …), but only
         when doing so leaves a substantial body intact (guards against a
         spurious early match nuking a short JD).
      2. Footer cut-off — drop everything from the first closing/CTA marker
         (Interested? / How to apply / Our process / Similar jobs / Terminal X …)
         onward, provided real content precedes it.
      3. Noise scrub — remove standalone noise lines (Terminal X, sidebar nav
         links, "Similar jobs", social/footer boilerplate).
    """
    if not text:
        return ""

    # ── Pass 1: lock on to the first real section header ──────────────────────
    lower = text.lower()
    start_idx = -1
    for header in _JD_START_HEADERS:
        idx = lower.find(header)
        if idx != -1 and (start_idx == -1 or idx < start_idx):
            start_idx = idx
    # Only trim the prefix when the header isn't already at the top and the
    # remaining body is substantial.
    if start_idx > 40 and (len(text) - start_idx) >= 150:
        text  = text[start_idx:]
        lower = lower[start_idx:]

    # ── Pass 2: cut from the first closing / CTA marker ───────────────────────
    end_idx = -1
    for marker in _JD_END_MARKERS:
        idx = lower.find(marker)
        # Require real content before the marker so a JD opening with e.g.
        # "Interested?" isn't truncated to nothing.
        if idx > 200 and (end_idx == -1 or idx < end_idx):
            end_idx = idx
    if end_idx != -1:
        text = text[:end_idx]

    # ── Pass 3: scrub standalone noise lines ──────────────────────────────────
    kept: list[str] = []
    for line in text.splitlines():
        if line.strip() and _NOISE_LINE_RE.match(line.strip()):
            continue
        kept.append(line)

    return "\n".join(kept).strip()


def _preprocess_jd(text: str) -> str:
    """
    Clean raw scraped JD text before passing it to the LLM so the model sees
    only actual job-description content.

    Steps:
      1. Truncate at "other jobs" / footer noise anchors.
      2. Strip lines that are pure boilerplate (cookie/privacy/social noise).
      3. Collapse duplicate consecutive section headers.
      4. Normalise excessive blank lines.
    """
    import re as _re

    # 1. Truncate at footer/sidebar anchors (case-insensitive).
    _CUTOFFS = (
        "similar jobs", "people also viewed", "more jobs like this",
        "recommended jobs", "jobs you may like", "other openings",
        "© ", "all rights reserved", "privacy policy", "cookie policy",
        "terms of service", "terms of use",
    )
    lower = text.lower()
    for anchor in _CUTOFFS:
        idx = lower.find(anchor)
        if idx > 200:       # only truncate if some real content precedes it
            text  = text[:idx]
            lower = lower[:idx]
            break

    # 2. Strip pure-boilerplate lines.
    _BOILERPLATE_RE = _re.compile(
        r"^\s*("
        r"cookie(s| policy| settings)?|privacy policy|terms of (service|use)|"
        r"all rights reserved|copyright \d{4}|©|"
        r"sign (in|up)|log in|create an? account|"
        r"share (this|job|post)|follow us|subscribe|newsletter|"
        r"apply now|easy apply|back to (search|results)|"
        r"report (this|job)|save (this|job)|dismiss"
        r")\s*$",
        _re.I,
    )
    lines = [l for l in text.splitlines() if not _BOILERPLATE_RE.match(l)]

    # 3. Collapse duplicate consecutive section headers (e.g. "Requirements\nRequirements").
    deduped: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (deduped
                and stripped
                and stripped.lower() == deduped[-1].strip().lower()
                and len(stripped) < 80):
            continue
        deduped.append(line)

    # 4. Collapse runs of more than 2 blank lines into a single blank line.
    result = _re.sub(r"\n{3,}", "\n\n", "\n".join(deduped))
    return result.strip()


def structure_jd(raw_text: str) -> Optional[str]:
    """
    Call the LLM to turn raw JD text into a Pydantic-validated JSON string.

    Single attempt only.  If the LLM output fails schema validation the error
    is logged once and None is returned — callers must treat None as a hard
    failure (status='failed') and must NOT retry in a loop.

    Pipeline:
      1. Nuclear JD cleaning  (_clean_raw_jd)   — strip site chrome/sidebars.
      2. Pre-processing        (_preprocess_jd)  — normalise whitespace/headers.
      3. LLM call              (claude-haiku)    — single attempt, strict prompt.
      4. Pydantic validation   (_parse_and_validate) — fail fast on bad output.

    Returns a compact JSON string on success, or None on failure.
    """
    if not raw_text or len(raw_text.strip()) < 200:
        logger.debug("[jd_structure] Input too short (%d chars) — skipping LLM call",
                     len(raw_text.strip()))
        return None

    content = _preprocess_jd(_clean_raw_jd(raw_text))[:8000]

    if len(content) < 200:
        logger.warning(
            "[jd_structure] Content shrank to %d chars after cleaning — "
            "nuclear cleaner may have over-stripped; returning None",
            len(content),
        )
        return None

    client = _build_client()
    try:
        message = client.messages.create(
            model      = _MODEL,
            max_tokens = 1024,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": content}],
        )
        raw = (message.content[0].text or "").strip()
    except Exception as exc:
        logger.error("[jd_structure] LLM call failed: %s", exc)
        return None

    validated = _parse_and_validate(raw)
    if validated is None:
        # Error already logged with full detail inside _parse_and_validate.
        logger.error(
            "[jd_structure] Returning None — caller must set status='failed'. "
            "Do NOT retry."
        )
        return None

    logger.info(
        "[jd_structure] Succeeded — company='%s' %d responsibilities, %d requirements",
        validated.company_name, len(validated.responsibilities), len(validated.requirements),
    )
    return validated.model_dump_json()


# ── Job-board / aggregator names to reject when overwriting job.company ───────
_PLATFORM_NAMES: frozenset[str] = frozenset({
    "linkedin", "indeed", "glassdoor", "ziprecruiter", "monster", "careerjet",
    "simplyhired", "snagajob", "dice", "ladders", "hired", "angellist", "wellfound",
    "greenhouse", "lever", "workday", "smartrecruiters", "jobvite", "icims",
    "talent", "jobs", "careers", "recruiting",
})


def extract_company_from_structured(structured_json: str) -> str:
    """
    Parse the structured JD JSON and return the extracted company_name if it is
    a real company (not empty, not a job-board name).  Returns "" otherwise.

    Callers use this to overwrite job.company after structure_jd() succeeds,
    fixing the bug where the scraper stores the platform name instead of the
    actual hiring company.
    """
    if not structured_json:
        return ""
    try:
        data = json.loads(structured_json)
        name = (data.get("company_name") or "").strip()
        if not name:
            return ""
        if name.lower().rstrip(".") in _PLATFORM_NAMES:
            logger.debug(
                "[jd_structure] company_name='%s' looks like a platform name — ignoring", name
            )
            return ""
        return name
    except (json.JSONDecodeError, AttributeError):
        return ""
