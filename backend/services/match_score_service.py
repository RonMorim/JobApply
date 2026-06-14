"""
Match Score Service — Three-Component Composite Scorer
======================================================

Architecture
------------
Scoring is split into two phases that map directly to the pipeline stages:

  Phase A  compute_local_proxy_score()          ← called in s1 (Scraper)
  ─────────────────────────────────────────────────────────────────────
  Pure Python, < 1 ms.  Evaluates job title keyword alignment and
  seniority fit against the candidate's level.  No network calls.
  Returns a 0-100 float that is stored immediately when a job is
  saved so the UI shows something useful before s2 runs.

  Phase B  compute_full_match_score_async()      ← called in s2 (Sourcing Specialist)
  ─────────────────────────────────────────────────────────────────────
  Combines Phase A with two LLM sub-scores via a single claude-haiku call
  (temperature=0.0 for determinism).  Weights:

    30%  Local title + seniority alignment  (Phase A result)
    50%  Semantic experience fit            (LLM: domain, hard skills, SaaS/Fintech/B2B2C)
    20%  Management trajectory fit          (LLM: leadership, cross-functional ownership)

  Final score = 0.30 × local + 0.50 × semantic + 0.20 × management

  Also runs _phase1() for the rich keyword/skills breakdown used by the
  tag row in the UI (matched_keywords, missing_skills, etc.).

Backwards Compatibility
-----------------------
compute_match_score_async(cv_data, jd_text, run_llm_validation, skill_proficiencies)
  — preserved signature, used by resumes.py (10+ call sites) and jobs.py.
  When run_llm_validation=True → full 3-component LLM composite.
  When run_llm_validation=False → Phase A + Phase 1 pure Python only (fast).

compute_match_score(cv_data, jd_text, …)
  — synchronous, Phase 1 only (no event loop available).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Candidate anchor ──────────────────────────────────────────────────────────
# Ron Morim's current seniority band — used as the reference point for all
# seniority alignment calculations.  Update when the candidate's target level
# changes (e.g., post-promotion pivot to senior IC or people-manager track).
_CANDIDATE_SENIORITY_LEVEL = 4   # "manager" = mid-to-senior PM, see _SENIORITY_BANDS

# ── Title keyword tiers ───────────────────────────────────────────────────────
# Controls the title alignment component of compute_local_proxy_score().
# Tier 1 = direct role match (90 pts), Tier 2 = abbreviation/partial (72),
# Tier 3 = adjacent CS/AM domain (68), "product" alone (55), no signal (28).

_TITLE_TIER_1: tuple[str, ...] = (
    "product manager", "product owner", "group product manager",
    "head of product", "vp of product", "vp product",
    "director of product", "product lead", "product operations manager",
    "product operations", "product management",
)
_TITLE_TIER_2: tuple[str, ...] = (
    " pm ", "pm,", "(pm)", "pm/", "pm-", " pm\n",
    "product strategy", "product growth", "digital product",
)
_TITLE_TIER_3: tuple[str, ...] = (
    "customer success", "csm", "account manager", "key account",
    "partnership manager", "client success", "customer experience manager",
)

# ── Seniority bands ───────────────────────────────────────────────────────────
_SENIORITY_BANDS: dict[str, int] = {
    "intern":      1,
    "junior":      2,
    "associate":   2,
    "coordinator": 2,
    "specialist":  3,
    "mid":         3,
    "manager":     4,
    "senior":      4,
    "lead":        5,
    "principal":   6,
    "staff":       6,
    "head":        7,
    "director":    7,
    "vp":          8,
    "vice president": 8,
}
_SENIORITY_ALIGNMENT: dict[int, float] = {0: 1.0, 1: 0.7, 2: 0.4}
_SENIORITY_MISMATCH_FACTOR = 0.1

# ── English stopwords ─────────────────────────────────────────────────────────
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must", "ought",
    "we", "you", "they", "he", "she", "it", "i", "our", "your", "their",
    "this", "that", "these", "those", "not", "no", "nor", "so", "yet",
    "both", "either", "neither", "from", "into", "through", "during",
    "including", "until", "against", "among", "throughout", "toward",
    "about", "above", "after", "before", "between", "out", "off", "over",
    "under", "again", "then", "once", "here", "there", "when", "where",
    "why", "how", "all", "each", "every", "few", "more", "most", "other",
    "than", "too", "very", "just", "only", "also", "well", "such",
    "if", "while", "although", "because", "since", "unless",
    "what", "who", "within", "across", "per", "up", "down",
})

# ── AI meta-phrase guard ──────────────────────────────────────────────────────
_AI_META_PREFIXES: tuple[str, ...] = (
    "no documented", "not mentioned", "no evidence", "no direct",
    "lacks", "limited", "unclear", "gap", "missing", "absent",
    "no experience", "no background", "no formal",
    "not demonstrated", "not stated", "not specified",
    "candidate does", "ron does", "ron has no", "ron lacks",
)

# ── Noise words ───────────────────────────────────────────────────────────────
_NOISE_WORDS = frozenset({
    "culture", "confidence", "passion", "passionate", "driven", "drive",
    "impact", "impactful", "ownership", "mindset", "attitude", "mission",
    "vision", "values", "diversity", "inclusion", "inclusive",
    "proactive", "innovative", "innovation", "dynamic", "startup",
    "excellence", "ideal", "thrive", "excited", "care",
    "role", "position", "candidate", "company", "organization", "team",
    "teams", "department", "group", "unit", "level", "track", "band",
    "opportunity", "hire", "hiring", "join", "joining", "looking",
    "seeking", "required", "preferred", "plus", "nice",
    "remote", "hybrid", "onsite", "fulltime", "office",
    "year", "years", "month", "months", "week", "weeks", "day", "days",
    "quarterly", "monthly", "weekly", "annual", "annually",
    # ── Geographic locations (global + Israeli cities) ────────────────────────
    "aviv", "york", "london", "berlin", "israel", "europe",
    "global", "local", "region", "area", "location",
    "herzliya", "raanana", "netanya", "petah", "tikva", "rehovot",
    "haifa", "beersheba", "rishon", "lezion", "ashdod", "ashkelon",
    "holon", "bnei", "brak", "modiin", "kfar", "saba", "hod", "hasharon",
    "givatayim", "ramat", "hasharon", "rosh", "haayin", "yehud",
    "jerusalem", "galilee", "negev", "sharon", "center", "south", "north",
    "dubai", "singapore", "amsterdam", "paris", "toronto", "boston",
    "seattle", "austin", "denver", "chicago", "angeles", "francisco",
    # ── English number words (caught by regex but not t.isnumeric()) ──────────
    "zero", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "eleven", "twelve", "hundred", "thousand",
    "first", "second", "third", "fourth", "fifth",
    # ── Generic adjectives / adverbs that slip past the main stopword list ────
    "strong", "excellent", "good", "great", "best", "top",
    "high", "low", "fast", "quick", "new", "current", "full", "part",
    "help", "ensure", "deliver", "provide", "support", "work", "working",
    "make", "build", "develop", "manage", "create", "use", "using",
    "maintain", "improve", "increase", "reduce", "achieve", "meet",
    "process", "processes", "solution", "solutions", "system", "systems",
    "platform", "tool", "tools", "report", "reporting", "data",
    "communication", "language", "written", "verbal",
    "experience", "ability", "skills", "skill", "knowledge", "understanding",
    "customer", "manager", "management", "specialist", "analyst",
    "associate", "coordinator", "executive", "consultant",
})

# ── Skill-signal patterns ─────────────────────────────────────────────────────
_SKILL_SIGNAL_PATTERNS = [
    r"experience\s+(?:with|in|using)\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"proficien(?:t|cy)\s+(?:with|in)\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"knowledge\s+of\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"familiarity\s+with\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"expertise\s+in\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"skilled\s+in\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
    r"(?:must|should)\s+(?:have|know)\s+([A-Za-z0-9\+\#\.\- ]{2,30})",
]

# ── Domain title signals for thin-proxy differentiation ──────────────────────
_DOMAIN_TITLE_SIGNALS: tuple[str, ...] = (
    "product", "manager", "owner", "senior", "lead", "head",
    "customer success", "csm", "account", "vp", "director",
    "group", "principal",
)

# ── Proficiency requirement signals ──────────────────────────────────────────
_REQUIRED_SIGNALS: frozenset[str] = frozenset({
    "required", "must have", "must-have", "you must", "expert",
    "professional experience", "strong", "minimum", "years of experience",
    "extensive", "demonstrated", "proven",
})
_PREFERRED_SIGNALS: frozenset[str] = frozenset({
    "nice to have", "nice-to-have", "familiarity", "knowledge of",
    "preferred", "bonus", "ideally", "helpful", "beneficial", "plus",
    "exposure to", "basic understanding", "awareness of",
})


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class MatchScoreResult:
    """
    Composite match score with full component breakdown.

    Three-component weights (when LLM is available):
      total = 0.30 × local_score + 0.50 × semantic_score + 0.20 × management_score

    The keyword_overlap / skills_alignment / seniority_alignment sub-scores
    come from _phase1() and power the tag row in the UI regardless of whether
    the LLM ran.
    """
    total:               float           # 0-100, 1 decimal
    keyword_overlap:     float           # 0-40  (Phase 1 component)
    skills_alignment:    float           # 0-35  (Phase 1 component)
    seniority_alignment: float           # 0-25  (Phase 1 component)
    matched_keywords:    list[str]       = field(default_factory=list)
    missing_keywords:    list[str]       = field(default_factory=list)
    matched_skills:      list[str]       = field(default_factory=list)
    missing_skills:      list[str]       = field(default_factory=list)
    suggestions:         list[str]       = field(default_factory=list)
    llm_validated:       bool            = False
    proficiency_notes:   list[str]       = field(default_factory=list)
    # ── Three-component sub-scores (0-100 each) ───────────────────────────────
    local_score:         float           = 0.0   # 30% — pure Python title+seniority
    semantic_score:      float           = 0.0   # 50% — LLM: domain + hard skills
    management_score:    float           = 0.0   # 20% — LLM: leadership + cross-func
    # ── LLM-generated fit brief ───────────────────────────────────────────────
    why_ron:             Optional[str]   = None  # populated by _llm_dual_score

    def as_dict(self) -> dict:
        return {
            "total":               self.total,
            "keyword_overlap":     self.keyword_overlap,
            "skills_alignment":    self.skills_alignment,
            "seniority_alignment": self.seniority_alignment,
            "matched_keywords":    self.matched_keywords,
            "missing_keywords":    self.missing_keywords,
            "matched_skills":      self.matched_skills,
            "missing_skills":      self.missing_skills,
            "suggestions":         self.suggestions,
            "llm_validated":       self.llm_validated,
            "proficiency_notes":   self.proficiency_notes,
            "local_score":         self.local_score,
            "semantic_score":      self.semantic_score,
            "management_score":    self.management_score,
            "why_ron":             self.why_ron,
        }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cv_to_text(cv_data: dict) -> str:
    parts: list[str] = [
        cv_data.get("title", ""),
        cv_data.get("summary", ""),
        cv_data.get("volunteering", ""),
    ]
    for exp in cv_data.get("experience", []):
        parts += [exp.get("role", ""), exp.get("company", "")]
        parts += (exp.get("bullets") or [])
    for edu in cv_data.get("education", []):
        parts += [edu.get("degree", ""), edu.get("honors", ""), edu.get("coursework", "")]
    for cat in (cv_data.get("skills") or {}).get("categories", []):
        parts.append(cat.get("label", ""))
        parts += cat.get("items", [])
    for lang in cv_data.get("languages", []):
        parts.append(lang.get("language", ""))
    return " ".join(p for p in parts if p).lower()


def _cv_experience_text(cv_data: dict) -> str:
    parts: list[str] = []
    for exp in cv_data.get("experience", []):
        parts.append(exp.get("role", ""))
        parts.append(exp.get("company", ""))
        parts += (exp.get("bullets") or [])
    return " ".join(p for p in parts if p).lower()


def _cv_declarative_text(cv_data: dict) -> str:
    parts: list[str] = [cv_data.get("title", ""), cv_data.get("summary", "")]
    for cat in (cv_data.get("skills") or {}).get("categories", []):
        parts.append(cat.get("label", ""))
        parts += cat.get("items", [])
    return " ".join(p for p in parts if p).lower()


def _is_experience_backed(term: str, exp_text: str) -> bool:
    if term in exp_text:
        return True
    tokens = [t for t in term.split() if len(t) >= 4]
    return bool(tokens) and any(tok in exp_text for tok in tokens)


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\+\#]{1,24}", text)
    result: set[str] = set()
    for w in words:
        lower = w.lower()
        if lower not in _STOPWORDS:
            result.add(lower)
        if len(w) >= 2 and w.isupper():
            result.add(lower)
    return result


def _extract_company_tokens(jd_text: str) -> set[str]:
    tokens: set[str] = set()
    head = jd_text[:150]
    match = re.search(r"\bat\s+(\S+(?:\s+\S+)?)", head, re.IGNORECASE)
    if match:
        for word in match.group(1).split()[:2]:
            word = re.split(r"[.!?,;]", word)[0]
            clean = re.sub(r"[^a-z0-9]", "", word.lower())
            if clean and len(clean) >= 2:
                tokens.add(clean)
    return tokens


def _is_ai_meta(phrase: str) -> bool:
    p = phrase.lower().strip()
    return any(p.startswith(prefix) for prefix in _AI_META_PREFIXES)


def _clean_phrase(raw: str) -> str:
    phrase = re.sub(r"\(.*?\)", "", raw)
    phrase = phrase.strip().lower().rstrip(".,;:()")
    if _is_ai_meta(phrase):
        return ""
    phrase = re.split(r"\.\s+[a-z]", phrase)[0]
    words = phrase.split()
    while words and (words[-1] in _STOPWORDS or words[-1] in _NOISE_WORDS):
        words.pop()
    return " ".join(words[:3]).strip()


def _extract_jd_skills(jd_text: str) -> list[str]:
    skills: list[str] = []
    seen: set[str] = set()
    lower = jd_text.lower()

    def _add(raw: str) -> None:
        phrase = _clean_phrase(raw)
        if phrase and phrase not in seen and len(phrase) >= 2:
            skills.append(phrase)
            seen.add(phrase)

    for pattern in _SKILL_SIGNAL_PATTERNS:
        for m in re.finditer(pattern, lower):
            _add(m.group(1))

    req_match = re.search(r"Required:\s*([^.!?\n]+)", jd_text, re.IGNORECASE)
    if req_match:
        for chunk in re.split(r"[,;•]", req_match.group(1)):
            _add(chunk)

    return skills


def _extract_jd_keywords(jd_text: str) -> set[str]:
    company_tokens = _extract_company_tokens(jd_text)
    combined_noise = _NOISE_WORDS | _STOPWORDS | company_tokens
    keywords: set[str] = set()

    def _is_clean(token: str) -> bool:
        t = token.lower().strip()
        return (
            len(t) >= 2
            and not t.isnumeric()
            and t not in combined_noise
            and not _is_ai_meta(t)
        )

    for m in re.finditer(r"\b[A-Z][A-Z0-9]{1,9}\b", jd_text):
        token = m.group(0).lower()
        if _is_clean(token):
            keywords.add(token)

    req_match = re.search(r"Required:\s*([^.!?\n]+)", jd_text, re.IGNORECASE)
    if req_match:
        for chunk in re.split(r"[,;•]", req_match.group(1)):
            phrase = _clean_phrase(chunk)
            if phrase and _is_clean(phrase.split()[0]):
                keywords.add(phrase)

    for skill in _extract_jd_skills(jd_text):
        words = skill.lower().split()
        clean_words: list[str] = []
        for w in words:
            if w in combined_noise or w in _STOPWORDS or "." in w:
                break
            clean_words.append(w)
        phrase = " ".join(clean_words[:3]).strip()
        if phrase and _is_clean(phrase.split()[0]):
            keywords.add(phrase)

    words = re.findall(r"\b[a-z][a-z0-9]{3,24}\b", jd_text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if _is_clean(w):
            freq[w] = freq.get(w, 0) + 1
    for w, count in freq.items():
        if count >= 3:
            keywords.add(w)

    return keywords


def _extract_cv_skills(cv_data: dict) -> list[str]:
    skills: list[str] = []
    for cat in (cv_data.get("skills") or {}).get("categories", []):
        for item in cat.get("items", []):
            if item:
                skills.append(item.lower().strip())
    return skills


def _detect_seniority(text: str) -> int:
    lower = text.lower()
    for keyword, level in sorted(_SENIORITY_BANDS.items(), key=lambda x: -x[1]):
        if keyword in lower:
            return level
    return 3


def _detect_jd_requirement_level(keyword: str, jd_text: str) -> str:
    lower_jd = jd_text.lower()
    kw_lower  = keyword.lower()
    required_hits = preferred_hits = 0
    start = 0
    while True:
        pos = lower_jd.find(kw_lower, start)
        if pos == -1:
            break
        window = lower_jd[max(0, pos - 150): pos + 80]
        for sig in _REQUIRED_SIGNALS:
            if sig in window:
                required_hits += 1
        for sig in _PREFERRED_SIGNALS:
            if sig in window:
                preferred_hits += 1
        start = pos + 1
    return "preferred" if preferred_hits > required_hits else "required"


def _proficiency_weight(user_level: str, jd_level: str) -> tuple[float, str]:
    if user_level in ("professional", "unknown", ""):
        return 1.0, ""
    if user_level == "academic":
        if jd_level == "preferred":
            return 0.9, "Academic (meets familiarity req.)"
        return 0.4, "Academic vs. Professional req."
    if user_level == "none":
        if jd_level == "preferred":
            return 0.3, "No exp. (preferred only)"
        return 0.0, "No exp. (required)"
    return 1.0, ""


def _resolve_proficiency(skill: str, proficiencies: dict[str, str]) -> tuple[str, str]:
    if not proficiencies:
        return "", ""
    if skill in proficiencies:
        return proficiencies[skill], skill
    skill_words = skill.lower().split()
    for tok in skill_words:
        if tok in proficiencies:
            return proficiencies[tok], tok
    for stored_skill, level in proficiencies.items():
        stored_words = set(stored_skill.lower().split())
        if stored_words & set(skill_words):
            overlap = stored_words & set(skill_words)
            return level, next(iter(overlap))
    return "", ""


# ── Confidence-Matrix skill scorer ───────────────────────────────────────────
#
# Replaces the binary matched/missing check with a graduated, confidence-
# weighted alternative when the Active Confidence Matrix is populated.
#
# Feature-flag pattern: if engine or user_id are None the function returns
# (None, None, None) and _phase1() falls back to the original binary logic.
# This keeps the scoring pipeline stable during the rollout period.

def _confidence_weighted_skill_score(
    jd_skills: list[str],
    engine,
    user_id: str | None,
    max_points: float = 35.0,
) -> tuple[float | None, list[str] | None, list[str] | None]:
    """
    Score the skills_alignment component using confidence scores from
    profile_entities instead of a binary matched/missing check.

    Algorithm
    ---------
    For each JD skill:
      1. Look up the entity in profile_entities by normalized_name.
         If not found, try a prefix fuzzy-match (first token of the skill name).
      2. credit = confidence_score / 100   (0.0–1.0)
         Missing entity → credit = 0.0
      3. score = (Σ credit / len(jd_skills)) × max_points

    The display labels include the confidence percentage so the UI can show
    "sprint prioritization (74%)" rather than a bare boolean match.

    Parameters
    ----------
    jd_skills : list[str]
        Skill phrases extracted from the JD by _extract_jd_skills().
    engine : sqlalchemy.engine.Engine | None
        The shared ENGINE from db.py.  None → returns (None, None, None).
    user_id : str | None
        Owning user.  None → returns (None, None, None).
    max_points : float
        Upper bound of the component (mirrors the binary path's 35 pts).

    Returns
    -------
    (score, matched_labels, missing_labels) — or (None, None, None) when
    the Confidence Matrix is unavailable (feature flag off / no DB).
    """
    if not engine or not user_id or not jd_skills:
        return None, None, None

    try:
        from sqlalchemy import text as _text
        matched: list[str] = []
        missing: list[str] = []
        credit_sum = 0.0

        with engine.connect() as conn:
            for skill in jd_skills:
                normalized = skill.strip().lower().replace(" ", "_").replace("-", "_")

                # Exact normalized match
                row = conn.execute(
                    _text(
                        "SELECT confidence_score FROM profile_entities "
                        "WHERE user_id = :u AND normalized_name = :n "
                        "LIMIT 1"
                    ),
                    {"u": user_id, "n": normalized},
                ).fetchone()

                # Prefix fuzzy match (first token, e.g. "sprint" from "sprint_prioritization")
                if not row:
                    first_token = normalized.split("_")[0]
                    if len(first_token) >= 4:
                        row = conn.execute(
                            _text(
                                "SELECT confidence_score FROM profile_entities "
                                "WHERE user_id = :u AND normalized_name LIKE :pat "
                                "ORDER BY confidence_score DESC LIMIT 1"
                            ),
                            {"u": user_id, "pat": f"%{first_token}%"},
                        ).fetchone()

                if row and float(row[0]) > 0:
                    conf   = float(row[0])
                    credit = conf / 100.0
                    credit_sum += credit
                    matched.append(f"{skill} ({conf:.0f}%)")
                else:
                    missing.append(skill)

        denom = max(len(jd_skills), 1)
        score = round((credit_sum / denom) * max_points, 1)
        return score, matched, missing

    except Exception as exc:
        logger.warning(
            "match_score: _confidence_weighted_skill_score failed (%s) — "
            "falling back to binary skill check",
            exc,
        )
        return None, None, None


# ── Phase 1: pure-Python keyword/skills/seniority scoring ────────────────────

def _phase1(
    cv_data: dict,
    jd_text: str,
    skill_proficiencies: dict[str, str] | None = None,
    # ── Confidence Matrix integration (optional) ─────────────────────────────
    # When both are provided, the skills_alignment component uses verified
    # confidence scores instead of binary matching.  Pass None (default) to
    # keep the original behaviour during the rollout period.
    cm_engine=None,      # sqlalchemy.engine.Engine from db.ENGINE
    cm_user_id: str | None = None,
) -> MatchScoreResult:
    """
    Pure Python scoring — no network calls, < 5 ms for typical inputs.

    Produces the keyword/skills/seniority breakdown used by the UI tag row.
    Also powers the fallback total when run_llm_validation=False.

    Components:
      keyword_overlap     0-40 pts
      skills_alignment    0-35 pts  (confidence-weighted when cm_engine + cm_user_id set)
      seniority_alignment 0-25 pts
    """
    exp_text = _cv_experience_text(cv_data)
    jd_keywords = _extract_jd_keywords(jd_text)

    if len(jd_keywords) < 3:
        logger.warning(
            "match_score Phase1: thin proxy — only %d keyword(s) extracted "
            "from %d chars of JD text.",
            len(jd_keywords), len(jd_text),
        )

    profs: dict[str, str] = skill_proficiencies or {}
    proficiency_notes: list[str] = []

    # ── Component 1: Keyword Overlap (40 pts) ─────────────────────────────────
    matched_kw: list[str] = []
    missing_kw: list[str] = []
    kw_weight_sum = 0.0

    for kw in sorted(jd_keywords):
        if kw not in exp_text:
            missing_kw.append(kw)
            continue
        user_level, matched_tok = _resolve_proficiency(kw, profs)
        if user_level and user_level not in ("professional", "unknown"):
            jd_level      = _detect_jd_requirement_level(kw, jd_text)
            weight, label = _proficiency_weight(user_level, jd_level)
            if label:
                note = f"{matched_tok or kw}: {label}"
                if note not in proficiency_notes:
                    proficiency_notes.append(note)
            if weight >= 0.5:
                matched_kw.append(kw)
            else:
                missing_kw.append(kw)
            kw_weight_sum += weight
        else:
            matched_kw.append(kw)
            kw_weight_sum += 1.0

    kw_denom = max(len(jd_keywords), 1)
    score_1   = round((kw_weight_sum / kw_denom) * 40, 1)

    # ── Component 2: Skills Alignment (35 pts) ────────────────────────────────
    jd_skills  = _extract_jd_skills(jd_text)

    # ── Confidence Matrix path (active when cm_engine + cm_user_id supplied) ──
    # This replaces the binary matched/missing check with a graduated score
    # derived from the user's verified confidence in each skill.
    _cm_score, _cm_matched, _cm_missing = _confidence_weighted_skill_score(
        jd_skills, cm_engine, cm_user_id
    )
    if _cm_score is not None:
        # Confidence Matrix available — use its output directly.
        score_2        = _cm_score
        matched_skills = _cm_matched or []
        missing_skills = _cm_missing or []
        logger.debug(
            "match_score Phase1 Component2: confidence-matrix path "
            "score=%.1f matched=%d missing=%d",
            score_2, len(matched_skills), len(missing_skills),
        )
    else:
        # ── Binary fallback (original behaviour) ─────────────────────────────
        cv_skills  = _extract_cv_skills(cv_data)
        cv_skill_tokens: set[str] = {
            tok for cs in cv_skills
            for tok in cs.split()
            if len(tok) >= 2 and tok not in _STOPWORDS
        }
        skill_targets: list[str] = list(jd_skills)
        if len(skill_targets) < 3:
            extra = [kw for kw in sorted(jd_keywords) if kw not in {s.split()[0] for s in skill_targets}]
            skill_targets = list(jd_skills) + extra

        matched_skills: list[str] = []
        missing_skills: list[str] = []
        skill_weight_sum = 0.0

        for js in skill_targets:
            js_tokens = set(js.split())
            js_base   = js.split()[0]
            if not _is_experience_backed(js, exp_text):
                missing_skills.append(js)
                continue
            if any(js == cs for cs in cv_skills):
                base_weight = 1.0; matched_skills.append(js)
            elif any(js in cs or cs in js for cs in cv_skills):
                base_weight = 0.8; matched_skills.append(js)
            elif js_tokens & cv_skill_tokens:
                base_weight = 0.6; matched_skills.append(js)
            elif js in exp_text:
                base_weight = 0.4; matched_skills.append(js)
            else:
                missing_skills.append(js); continue
            user_level, matched_tok = _resolve_proficiency(js, profs)
            if user_level and user_level not in ("professional", "unknown"):
                jd_level      = _detect_jd_requirement_level(js, jd_text)
                prof_w, label = _proficiency_weight(user_level, jd_level)
                if label:
                    note = f"{matched_tok or js_base}: {label}"
                    if note not in proficiency_notes:
                        proficiency_notes.append(note)
                skill_weight_sum += base_weight * prof_w
            else:
                skill_weight_sum += base_weight

        skills_denom = max(len(skill_targets), 1)
        score_2      = round((skill_weight_sum / skills_denom) * 35, 1)
    # ── end Component 2 ───────────────────────────────────────────────────────

    # ── Component 3: Seniority Alignment (25 pts) ─────────────────────────────
    jd_title_block  = jd_text[:200]
    cv_title        = cv_data.get("title", "")
    cv_recent_role  = (cv_data.get("experience") or [{}])[0].get("role", "")
    jd_seniority    = _detect_seniority(jd_title_block)
    cv_seniority    = _detect_seniority(f"{cv_title} {cv_recent_role}")
    delta           = abs(jd_seniority - cv_seniority)
    factor          = _SENIORITY_ALIGNMENT.get(delta, _SENIORITY_MISMATCH_FACTOR)
    score_3         = round(factor * 25, 1)

    total = round(min(100.0, score_1 + score_2 + score_3), 1)

    # ── Post-processing: thin-proxy differentiation ───────────────────────────
    jd_has_rich_signal = len(jd_keywords) >= 3
    if not jd_has_rich_signal:
        total = min(total, 70.0)
        title_lower  = jd_title_block.lower()
        title_hits   = sum(1 for sig in _DOMAIN_TITLE_SIGNALS if sig in title_lower)
        title_bonus  = min(4.0, float(title_hits))
        total        = min(70.0, round(total + title_bonus, 1))
        _fp          = int(hashlib.md5(jd_text[:80].encode("utf-8", errors="ignore")).hexdigest()[:4], 16)
        variance     = round((_fp % 51 - 25) / 10, 1)
        total        = min(70.0, max(50.0, round(total + variance, 1)))
        logger.debug(
            "match_score: thin-proxy cap=70.0 title_bonus=+%.1f variance=%+.1f → %.1f",
            title_bonus, variance, total,
        )
    else:
        if "product" in jd_title_block.lower():
            total = min(100.0, round(total + 5.0, 1))

    _SENIOR_CONFLICT_THRESHOLD = 5
    if jd_seniority >= _SENIOR_CONFLICT_THRESHOLD and cv_seniority < _SENIOR_CONFLICT_THRESHOLD:
        total = max(0.0, round(total - 10.0, 1))

    total = round(min(100.0, max(0.0, total)), 1)

    logger.debug(
        "match_score Phase1: kw=%.1f/40 skills=%.1f/35 seniority=%.1f/25 → %.1f",
        score_1, score_2, score_3, total,
    )

    return MatchScoreResult(
        total               = total,
        keyword_overlap     = float(score_1),
        skills_alignment    = float(score_2),
        seniority_alignment = float(score_3),
        matched_keywords    = matched_kw[:20],
        missing_keywords    = missing_kw[:20],
        matched_skills      = matched_skills,
        missing_skills      = missing_skills,
        suggestions         = [
            f"Consider adding: {s}"
            for s in missing_skills[:5]
            if not _is_ai_meta(s)
        ],
        llm_validated       = False,
        proficiency_notes   = proficiency_notes,
    )


# ── Phase A: Local proxy score (30% component) ───────────────────────────────

def compute_local_proxy_score(job_title: str, jd_text: str = "") -> float:
    """
    Fast pure-Python proxy score — the 30% local component of the composite.

    Evaluates two signals:
      60%  Title keyword alignment — does the job title match PM/CS tiers?
      40%  Seniority alignment    — does the role level fit the candidate's band?

    Returns 0-100.  Completes in < 1 ms.

    Called by MatcherAgent in s1 so jobs enter the DB with a meaningful initial
    score before the s2 LLM enrichment runs.  The candidate anchor level is
    _CANDIDATE_SENIORITY_LEVEL = 4 ("manager" / mid-senior PM).
    """
    title_lower = job_title.lower().strip()

    # ── 60%: Title keyword alignment ─────────────────────────────────────────
    if any(sig in title_lower for sig in _TITLE_TIER_1):
        title_score = 90.0
    elif any(sig in title_lower for sig in _TITLE_TIER_2):
        title_score = 72.0
    elif any(sig in title_lower for sig in _TITLE_TIER_3):
        title_score = 68.0
    elif "product" in title_lower:
        title_score = 55.0
    else:
        title_score = 28.0

    # ── 40%: Seniority alignment ──────────────────────────────────────────────
    probe_text       = f"{job_title} {jd_text[:200]}"
    jd_seniority     = _detect_seniority(probe_text)
    delta            = abs(jd_seniority - _CANDIDATE_SENIORITY_LEVEL)
    seniority_factor = _SENIORITY_ALIGNMENT.get(delta, _SENIORITY_MISMATCH_FACTOR)
    seniority_score  = round(seniority_factor * 100.0, 1)

    local = round(0.60 * title_score + 0.40 * seniority_score, 1)
    result = min(100.0, max(0.0, local))

    logger.debug(
        "local_proxy: title='%s' → tier_score=%.0f seniority=%d→factor=%.1f → %.1f",
        job_title, title_score, jd_seniority, seniority_factor, result,
    )
    return result


# ── Phase B LLM sub-scorer: semantic + management (50% + 20% components) ─────

_LLM_SYSTEM_SCORER = (
    "You are a precise ATS scoring engine. "
    "Output ONLY a valid, complete JSON object — no markdown fences, no prose, no explanation. "
    "The entire response must be parseable by json.loads(). "
    "Keep the 'why_apply' field under 250 characters to avoid truncation."
)

_LLM_SCORER_TEMPLATE = """\
Score this JOB vs. CANDIDATE across two independent dimensions.
Return ONLY valid JSON — no markdown, no extra text.

JOB TITLE: {job_title}
HIRING COMPANY: {company_name}

JOB DESCRIPTION (first 800 chars):
{jd_excerpt}

CANDIDATE SUMMARY:
{cv_summary}

CANDIDATE SKILLS:
{cv_skills}

CANDIDATE EXPERIENCE (most recent first):
{cv_experience}
{company_legacy_note}
Return this exact JSON object:
{{
  "semantic_experience_score": <integer 0-100>,
  "management_trajectory_score": <integer 0-100>,
  "why_apply": "<concise fit rationale — max 250 characters>"
}}

WHY_APPLY RULES:
  • Plain text, no markdown, no bullet symbols, no newlines.
  • One or two sentences: state the strongest fit signal and the main gap (if any).
  • Direct and factual — no filler ("great opportunity", "excited to").
  • Hard limit: ≤ 250 characters total. Truncate rather than exceed.

══════════════════════════════════════════════════════════
MANDATORY ARCHITECTURAL PRINCIPLES — override all defaults
══════════════════════════════════════════════════════════

1. EXPLORATION FREEDOM
   DO NOT penalize the candidate for exploring a different career direction or
   for a title mismatch between their current/most-recent role and this JD.
   Evaluate TRANSFERABLE CAPABILITIES across the FULL experience history.
   If the underlying skill exists anywhere in their record, credit it fully.

2. SENIORITY SCALING
   Overqualification is NEVER a penalty — treat it as a positive signal.
   If the candidate has MORE seniority or MORE years of experience than the JD
   requires (e.g., Team Lead applying for an IC role; 3+ years when 1–2 are
   asked), score that at the SAME level as an exact match or HIGHER.
   Never discount a score because the candidate is "too senior".

3. COMPANY LEGACY  (see CRITICAL override block above if present)
   Any prior employment at the target company is the strongest possible fit
   signal — validated culture, domain, product, and org-chart knowledge.
   Prior employer history must result in a top-tier score for both dimensions.

══════════════════════════════════════════════════════════
SCORING CRITERIA
══════════════════════════════════════════════════════════

COMPANY CONTEXT — factor this into semantic_experience_score
  Use the HIRING COMPANY field above to assess environment fit:
  • Stage fit: hyper-growth startup, scale-up, enterprise, or public company?
    The candidate's background is strongest in high-growth B2B SaaS / scale-up
    environments (Series B–D, 100–1000 employees, fast iteration culture).
    Matching that profile is a positive signal; large-enterprise or regulated-
    industry contexts (banks, telcos, government) should slightly lower the score
    unless the JD content itself shows the company operates in an agile way.
  • Domain fit: B2B SaaS, marketplace, fintech, e-commerce — weight positively.
  • Culture signals inferred from the company name may inform the why_apply brief
    but should not be the primary score driver — JD content takes precedence.

semantic_experience_score  — weight 50% of composite
  Evaluate domain alignment (SaaS / Fintech / E-commerce / B2B / B2B2C) AND
  hard-skill overlap with JD requirements across the candidate's ENTIRE record.
  Factor in company stage/culture fit (see COMPANY CONTEXT above).
  Career-pivot exploration must NOT lower this score — focus on transferability.
  90-100 = exceptional domain + skills fit (or validated prior employer).
  70-89  = strong transferable match, minor gaps.
  50-69  = solid partial match, bridgeable with ramp-up.
  30-49  = limited alignment, notable gaps.
  0-29   = poor fit, fundamental mismatch.

management_trajectory_score  — weight 20% of composite
  Does the candidate's record show leadership, people management, or
  cross-functional ownership — regardless of whether the JD requires it?
  Higher seniority than required = ASSET, score it at the top of the band.
  90-100 = clear leadership match (demonstrated and/or required).
  70-89  = good trajectory signals, minor gap.
  50-69  = some leadership evidence, partial match.
  30-49  = limited evidence or JD is IC-only.
  0-29   = no leadership evidence whatsoever.
"""


def _find_prior_employer(cv_data: dict, target_company: str) -> Optional[str]:
    """
    Return the first company from cv_data experience whose core name matches
    the target job's company name (case-insensitive whole-word), or None.

    Scope: compares ONLY against `target_company` (the job's company field),
    NOT against the full JD body.  Searching the body was the root cause of
    false positives — e.g. "River" (past restaurant job) matching inside Wolt's
    JD because the word "river" appeared in the description text.

    Matching rules:
      • Strips trailing parenthetical / dash suffixes before testing
        (e.g. "GO-OUT (Startup)" → "GO-OUT").
      • Uses regex word boundaries (\\b) so "River" does NOT match "Riverside".
      • re.escape() treats hyphens, dots, etc. as literals, not regex operators.
      • Minimum core length of 4 characters to skip short abbreviations.
    """
    if not target_company or not target_company.strip():
        return None

    for exp in cv_data.get("experience", []):
        company = (exp.get("company") or "").strip()
        if len(company) < 4:
            continue
        # Strip parenthetical/dash suffixes: "GO-OUT (Startup)" → "GO-OUT"
        core = re.split(r"\s*[\(\[–—]", company)[0].strip()
        if len(core) < 4:
            continue
        # Word-boundary match against the target company name only —
        # this prevents "River" from firing on Wolt's JD text.
        pattern = r"\b" + re.escape(core) + r"\b"
        if re.search(pattern, target_company, re.IGNORECASE):
            return company
    return None


def _parse_json_robust(raw: str, job_title: str = "") -> dict | None:
    """
    Parse the LLM JSON response, attempting progressively more aggressive
    repair strategies before giving up.

    Truncation pattern: the model fills `max_tokens` mid-string, producing
    something like:
        {"semantic_experience_score": 72, "management_trajectory_score": 65,
         "why_apply": "🟢 Core Strengths:\\n• Led product at GO-OUT
    (no closing quote, comma, or brace)

    Repair order:
      1. Direct parse — succeeds for well-formed responses.
      2. Close open string + object  →  append  '"}
      3. Close object only           →  append  }
      4. Extract scores with regex, drop why_apply entirely.
      5. Return None  — caller uses (60, 60, "") fallback.
    """
    # 1. Direct
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 2. Close open string + object
    try:
        return json.loads(raw + '"}')
    except json.JSONDecodeError:
        pass

    # 3. Close object only
    try:
        return json.loads(raw + "}")
    except json.JSONDecodeError:
        pass

    # 4. Regex extraction — scores only, no why_apply
    sem_m  = re.search(r'"semantic_experience_score"\s*:\s*(\d+)',   raw)
    mgmt_m = re.search(r'"management_trajectory_score"\s*:\s*(\d+)', raw)
    if sem_m or mgmt_m:
        logger.warning(
            "match_score LLM: truncated JSON repaired via regex for title='%s' — "
            "scores recovered but why_apply lost. raw=%r",
            job_title, raw[:200],
        )
        return {
            "semantic_experience_score":   int(sem_m.group(1))  if sem_m  else 60,
            "management_trajectory_score": int(mgmt_m.group(1)) if mgmt_m else 60,
            "why_apply": "",
        }

    # 5. Unrecoverable
    logger.warning(
        "match_score LLM: unrecoverable JSON for title='%s' — raw=%r",
        job_title, raw[:300],
    )
    return None


async def _llm_dual_score(
    cv_data: dict,
    jd_text: str,
    job_title: str = "",
    company_name: str = "",
) -> tuple[float, float, str]:
    """
    Single claude-haiku-4-5 call returning (semantic_score, management_score, why_apply).

    temperature=0.0 guarantees identical output for identical inputs (determinism).
    Falls back to (60.0, 60.0, "") on any API or parse error so the composite
    still gets a reasonable score and the pipeline never crashes.
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning(
            "match_score LLM: ANTHROPIC_API_KEY not set — returning neutral fallback scores"
        )
        return 60.0, 60.0, ""

    # ── Compact CV fields for the prompt ─────────────────────────────────────
    cv_summary = (cv_data.get("summary") or "")[:400]
    cv_skills  = ", ".join(
        item
        for cat in (cv_data.get("skills") or {}).get("categories", [])
        for item in cat.get("items", [])
    )[:300]

    # ── Experience: most-recent-first, full list, with brief bullet context ───
    # FIX: previously sliced to [:5] (oldest entries only) — all entries are now
    # included in reverse-chronological order so the LLM always sees the most
    # relevant recent roles first, regardless of how many entries exist.
    exp_lines: list[str] = []
    for e in reversed(cv_data.get("experience", [])):
        role    = e.get("role", "").strip()
        company = e.get("company", "").strip()
        bullets = e.get("bullets") or []
        line    = f"{role} @ {company}"
        if bullets and bullets[0]:
            # First 90 chars of the top bullet gives domain context without bloat
            snippet = bullets[0].strip()[:90].rstrip()
            line   += f" — {snippet}"
        exp_lines.append(line)
    cv_experience = "\n".join(exp_lines)

    # ── Company Legacy detection ──────────────────────────────────────────────
    # If the target company appears in the candidate's experience, inject a
    # mandatory high-priority override so the LLM correctly weights prior
    # employment as the strongest possible fit signal.
    prior_employer = _find_prior_employer(cv_data, company_name)
    if prior_employer:
        company_legacy_note = (
            "\n╔══════════════════════════════════════════════════════════╗\n"
            "║  CRITICAL — COMPANY LEGACY OVERRIDE (mandatory)          ║\n"
            "╚══════════════════════════════════════════════════════════╝\n"
            f"The candidate has PRIOR EMPLOYMENT at [{prior_employer}] — the EXACT\n"
            "company in this job posting. This is the strongest possible fit signal:\n"
            "  • Validated cultural fit (they already know the org, the people,\n"
            "    the mission, and the operating style).\n"
            "  • Validated domain fit (product, market, tech stack, client base).\n"
            "  • Zero onboarding ramp-up on context that external candidates spend\n"
            "    months acquiring.\n"
            "YOU MUST score semantic_experience_score ≥ 85 AND\n"
            "management_trajectory_score ≥ 80 unless there is an explicit,\n"
            "disqualifying hard-skill gap stated in the JD.\n"
        )
        logger.info(
            "match_score LLM: Company-Legacy override active — prior employer '%s' "
            "detected in JD for title='%s'",
            prior_employer, job_title,
        )
    else:
        company_legacy_note = ""

    prompt = _LLM_SCORER_TEMPLATE.format(
        job_title           = job_title or "Unknown Role",
        company_name        = company_name or "Unknown",
        jd_excerpt          = jd_text[:800].strip(),
        cv_summary          = cv_summary,
        cv_skills           = cv_skills,
        cv_experience       = cv_experience,
        company_legacy_note = company_legacy_note,
    )

    logger.debug(
        "match_score LLM: firing request for title='%s' company='%s' "
        "(jd_len=%d prompt_len=%d)",
        job_title, company_name, len(jd_text), len(prompt),
    )
    try:
        client  = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model       = "claude-haiku-4-5-20251001",
            max_tokens  = 400,   # raised from 220 — why_apply bullets need headroom
            temperature = 0.0,   # deterministic — same input → same output every time
            system      = _LLM_SYSTEM_SCORER,
            messages    = [{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        logger.debug(
            "match_score LLM: raw response for title='%s': %r",
            job_title, raw[:300],
        )

        # Strip optional markdown fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw   = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:]).strip()

        payload = _parse_json_robust(raw, job_title)
        if payload is None:
            return 60.0, 60.0, ""

        semantic   = max(0.0, min(100.0, float(payload.get("semantic_experience_score",   60))))
        management = max(0.0, min(100.0, float(payload.get("management_trajectory_score", 60))))
        why_apply  = str(payload.get("why_apply", "")).strip()

        logger.info(
            "match_score LLM: semantic=%.0f  management=%.0f  why_apply_len=%d  title='%s'",
            semantic, management, len(why_apply), job_title,
        )
        return semantic, management, why_apply

    except json.JSONDecodeError as exc:
        logger.warning(
            "match_score LLM: JSON parse failed for title='%s' (%s) — raw=%r — using fallback 60",
            job_title, exc, raw[:300] if 'raw' in dir() else '<no raw>',
        )
        return 60.0, 60.0, ""
    except Exception as exc:
        logger.warning(
            "match_score LLM: API call failed for title='%s': %s (%s)",
            job_title, type(exc).__name__, exc,
        )
        return 60.0, 60.0, ""


# ── Public API ────────────────────────────────────────────────────────────────

def compute_match_score(
    cv_data: dict,
    jd_text: str,
    run_llm_validation: bool = True,
    skill_proficiencies: dict[str, str] | None = None,
) -> MatchScoreResult:
    """
    Synchronous entry point — Phase 1 pure Python only (no event loop).

    Use compute_match_score_async inside async route handlers for the full
    3-component LLM composite.
    """
    return _phase1(cv_data, jd_text, skill_proficiencies)


async def compute_match_score_async(
    cv_data: dict,
    jd_text: str,
    run_llm_validation: bool = True,
    skill_proficiencies: dict[str, str] | None = None,
    job_title: str = "",
    company_name: str = "",
) -> MatchScoreResult:
    """
    Async composite scorer — primary entry point for route handlers.

    When run_llm_validation=True (default):
      Runs Phase 1 for keyword breakdown, then the LLM dual-scorer for the
      50% semantic + 20% management components.
      final = 0.30 × local + 0.50 × semantic + 0.20 × management

    When run_llm_validation=False:
      Phase 1 only — fast, no API calls.  Suitable for live-editor re-scores,
      force_rescore_all, and any latency-sensitive path.

    Parameters
    ----------
    cv_data : dict
        Structured CV in the standard format (title, experience, skills, …).
    jd_text : str
        Raw job description text.
    run_llm_validation : bool
        Whether to run the LLM sub-scorers.  Default True.
    skill_proficiencies : dict | None
        Optional {skill: level} map from master_profile_service.
    job_title : str
        Job title string — improves LLM prompt context and local proxy accuracy.
        If omitted, extracted from the first 60 chars of jd_text.
    company_name : str
        Target company name — used by _find_prior_employer to detect Company
        Legacy matches.  Must be passed from the job object, NOT derived from
        jd_text, to prevent false positives from body-text substring matches.
    """
    if not run_llm_validation:
        # Fast path — Phase 1 only
        return _phase1(cv_data, jd_text, skill_proficiencies)

    # Safety net: refuse to call the LLM on a placeholder / un-hydrated JD.
    # Sending "Title at Company in Location" to Claude wastes tokens and
    # produces a meaningless 60/60 fallback.  feed_service._enrich_one should
    # have fetched the real JD before reaching this point; this guard is the
    # last line of defence.
    #
    # BUG FIX: previously this returned _phase1() directly.  _phase1().total
    # can reach 94+ for an exact title match ("Senior Product Manager") even
    # when jd_text is only a title stub — a Phase-1-only score of 94 was then
    # stored as match_score, floating empty jobs to the top of the feed.
    #
    # Correct behaviour: thin JDs get semantic=0 and management=0 so the
    # composite formula caps at  0.30 × local + 0 + 0 ≤ ~28 for a perfect
    # title match.  This keeps un-hydrated jobs near the bottom of the list
    # without discarding the local/keyword breakdown the UI tag row needs.
    _LLM_MIN_JD_CHARS = 300
    if len(jd_text.strip()) < _LLM_MIN_JD_CHARS:
        inferred_title = job_title or jd_text[:60].split("\n")[0].strip()
        local          = compute_local_proxy_score(inferred_title, jd_text)
        composite      = round(0.30 * local, 1)   # semantic=0, management=0
        p1             = _phase1(cv_data, jd_text, skill_proficiencies)
        logger.warning(
            "match_score LLM: jd_text too thin (%d chars) — semantic=0 management=0 "
            "→ composite capped at %.1f (was incorrectly %.1f via Phase-1 only)",
            len(jd_text.strip()), composite, p1.total,
        )
        return MatchScoreResult(
            total               = composite,
            keyword_overlap     = p1.keyword_overlap,
            skills_alignment    = p1.skills_alignment,
            seniority_alignment = p1.seniority_alignment,
            matched_keywords    = p1.matched_keywords,
            missing_keywords    = p1.missing_keywords,
            matched_skills      = p1.matched_skills,
            missing_skills      = p1.missing_skills,
            suggestions         = p1.suggestions,
            llm_validated       = False,
            proficiency_notes   = p1.proficiency_notes,
            local_score         = local,
            semantic_score      = 0.0,
            management_score    = 0.0,
            why_ron             = None,
        )

    # ── Full 3-component composite ────────────────────────────────────────────

    # 30% — local proxy (pure Python title + seniority)
    inferred_title = job_title or jd_text[:60].split("\n")[0].strip()
    local = compute_local_proxy_score(inferred_title, jd_text)

    # 50% + 20% — LLM dual scorer (single haiku call, temperature=0.0)
    semantic, management, why_apply = await _llm_dual_score(cv_data, jd_text, inferred_title, company_name)

    # Composite
    composite = round(0.30 * local + 0.50 * semantic + 0.20 * management, 1)
    composite = min(100.0, max(0.0, composite))

    # Phase 1 for rich keyword/skills breakdown (populates UI tag row)
    p1 = _phase1(cv_data, jd_text, skill_proficiencies)

    logger.info(
        "match_score composite: local=%.1f(×.30) + semantic=%.1f(×.50) + "
        "management=%.1f(×.20) → %.1f  title='%s'",
        local, semantic, management, composite, inferred_title,
    )

    return MatchScoreResult(
        total               = composite,
        keyword_overlap     = p1.keyword_overlap,
        skills_alignment    = p1.skills_alignment,
        seniority_alignment = p1.seniority_alignment,
        matched_keywords    = p1.matched_keywords,
        missing_keywords    = p1.missing_keywords,
        matched_skills      = p1.matched_skills,
        missing_skills      = p1.missing_skills,
        suggestions         = p1.suggestions,
        llm_validated       = True,
        proficiency_notes   = p1.proficiency_notes,
        local_score         = local,
        semantic_score      = semantic,
        management_score    = management,
        why_ron             = why_apply or None,
    )
