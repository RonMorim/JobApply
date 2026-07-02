"""
ATS Match Engine — recruiter-grade scoring built on the Confidence Matrix.

This module is ADDITIVE. It does not modify or replace the existing composite
in match_score_service.py; integration is opt-in by the caller (see the
"Integration" note at the bottom).

Three layers, mirroring how Greenhouse/Workday screeners and human technical
recruiters actually evaluate:

  Layer 0  KNOCKOUT      — boolean hard constraints only (work model, location,
                           language, mandatory certification, MINIMUM years).
                           Never title match, never overqualification, never a
                           career pivot (CLAUDE.md Principle 3).
  Layer 1  COMPETENCIES  — JD must-haves / nice-to-haves mapped onto the user's
                           Confidence Matrix EntityScores. Evidence-backed
                           coverage, not keyword presence.
  Layer 2  IMPACT & SCALE — density of quantified scale signals in the
                           candidate's history vs. the scale the JD demands.

Compliance with Core AI Scoring Principles (CLAUDE.md):
  P1  No truncation      — competency extraction receives the FULL structured
                           JD; scale scan receives the FULL experience list.
  P2  Company legacy     — prior-employer detection floors the competency
                           layer at 85.0 (word-boundary regex, never substring).
  P3  Exploration freedom— knockouts are minimums-only; pivots and
                           overqualification are structurally unable to reduce
                           any layer's score.
  P4  Thin-JD fallback   — compute_ats_match raises ThinJdError below
                           _MIN_JD_CHARS so the caller keeps the existing
                           0.30 × local cap path.
  P5  Reviewed against P1–P4 before implementation.

All scores are rounded to exactly one decimal place.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MIN_JD_CHARS = 300   # keep in lock-step with _LLM_MIN_JD_CHARS in match_score_service

# ── Weights (single source of truth, documented in module docstring) ──────────

W_COMPETENCY = 0.60
W_IMPACT     = 0.25
W_LOCAL      = 0.15

W_MUST_HAVE  = 0.75
W_NICE_HAVE  = 0.25

KNOCKOUT_SOFT_FAIL_MULTIPLIER = 0.35   # soft cap, not zero — surfaced with reasons
COMPANY_LEGACY_COMPETENCY_FLOOR = 85.0

# Evidence quality multiplier — mirrors verification_level from confidence_math
VERIFICATION_MULTIPLIER: dict[str, float] = {
    "VERIFIED_MANUAL":    1.00,
    "ORCHESTRATION_ONLY": 0.85,
    "UNVERIFIED":         0.60,
}


class ThinJdError(ValueError):
    """Raised when the JD is too thin to score. Caller must fall back to 0.30 × local."""


class HeuristicJd(BaseModel):
    """Duck-typed stand-in for StructuredJd when the job has no structured JSON yet."""
    requirements: list[str] = Field(default_factory=list)
    advantages:   list[str] = Field(default_factory=list)


_REQ_HEADING  = re.compile(r"^\s*(requirements?|must[- ]haves?|qualifications|what you(?:'|’)ll need|who you are)\b", re.I)
_ADV_HEADING  = re.compile(r"^\s*(nice[- ]to[- ]haves?|advantages?|bonus|preferred|plus(?:es)?)\b", re.I)
_OTHER_HEADING = re.compile(r"^\s*(responsibilities|about (?:us|the role)|benefits|what you(?:'|’)ll do)\b", re.I)
_BULLET_LINE  = re.compile(r"^\s*[-•*·]\s*(.+)$")


def heuristic_structured_jd(jd_text: str) -> HeuristicJd:
    """
    Zero-LLM fallback JD splitter for shadow-mode scoring.

    Walks the JD line-by-line, tracking which section heading was last seen.
    Bullet lines under a requirements-style heading → must-haves; under an
    advantages-style heading → nice-to-haves. Bullets in unrecognised sections
    are ignored (responsibilities are duties, not candidate requirements).
    """
    section = None  # 'req' | 'adv' | None
    out = HeuristicJd()
    for line in jd_text.splitlines():
        if _REQ_HEADING.match(line):
            section = "req"
            continue
        if _ADV_HEADING.match(line):
            section = "adv"
            continue
        if _OTHER_HEADING.match(line):
            section = None
            continue
        m = _BULLET_LINE.match(line)
        if m and section == "req":
            out.requirements.append(m.group(1).strip())
        elif m and section == "adv":
            out.advantages.append(m.group(1).strip())
    return out


# ═════════════════════════════════════════════════════════════════════════════
# Data models
# ═════════════════════════════════════════════════════════════════════════════

class CompetencyTier(str, Enum):
    MUST_HAVE = "must_have"
    NICE_HAVE = "nice_have"


class JdCompetency(BaseModel):
    """One requirement extracted from the structured JD."""
    raw_text:   str                       # original bullet from the JD
    normalized: str                       # snake_case key, e.g. "product_management"
    tier:       CompetencyTier
    min_years:  Optional[float] = None    # parsed "X+ years" demand, if stated


class CompetencyMatch(BaseModel):
    """A JD competency resolved against the Confidence Matrix."""
    competency:         JdCompetency
    matched_entity:     Optional[str] = None   # EntityScore.name, None = no evidence
    confidence_score:   float = 0.0            # EntityScore.score (0–100)
    verification_level: str   = "UNVERIFIED"
    coverage:           float = 0.0            # confidence × verification multiplier, 0–1


class KnockoutRule(BaseModel):
    """One hard constraint parsed from the JD."""
    kind:        str            # 'work_model' | 'location' | 'language' | 'certification' | 'min_years'
    requirement: str            # human-readable demand
    passed:      Optional[bool] # None = cannot be evaluated from profile → treated as pass


class KnockoutResult(BaseModel):
    rules:      list[KnockoutRule] = Field(default_factory=list)
    passed:     bool  = True
    multiplier: float = 1.0
    reasons:    list[str] = Field(default_factory=list)


class ImpactDensityResult(BaseModel):
    candidate_signals: list[str] = Field(default_factory=list)  # extracted scale phrases
    jd_scale_demands:  list[str] = Field(default_factory=list)
    score:             float = 0.0                              # 0–100


class AtsMatchResult(BaseModel):
    """Full engine output. All floats carry exactly one decimal."""
    final_score:       float
    base_score:        float = 0.0  # pre-knockout composite; final = multiplier × base.
                                    # Callers that gate/cap on knockout themselves
                                    # (match_score_service unified composite) must
                                    # consume base_score to avoid double-penalising.
    knockout:          KnockoutResult
    competency_score:  float
    competency_detail: list[CompetencyMatch]
    impact:            ImpactDensityResult
    local_score:       float
    legacy_company:    Optional[str] = None    # set when Principle-2 floor applied
    gap_analysis:      list[str] = Field(default_factory=list)  # unmet must-haves


# ═════════════════════════════════════════════════════════════════════════════
# Layer 0 — Knockouts (hard constraints ONLY; minimums only)
# ═════════════════════════════════════════════════════════════════════════════

_WORK_MODEL_RE  = re.compile(r"\b(on[- ]?site only|fully on[- ]?site|no remote|office[- ]based only)\b", re.I)
_MIN_YEARS_RE   = re.compile(r"(?:minimum|at least|(?<![\w.]))(\d{1,2})\s*\+?\s*years?", re.I)
_LANGUAGE_RE    = re.compile(r"\b(native|fluent|proficient)\s+(english|hebrew|german|french|spanish)\b", re.I)
_CERT_MUST_RE   = re.compile(r"\b(must (?:hold|have)|required certification|mandatory)\b.{0,60}?\b(certification|certified|license[d]?)\b", re.I)


def _total_experience_years(cv_data: dict) -> float:
    """Sum the years spans in the experience list. Best-effort; unknown → 0."""
    total = 0.0
    for exp in cv_data.get("experience", []):
        years = exp.get("years") or exp.get("duration_years")
        if isinstance(years, (int, float)):
            total += float(years)
    return total


def evaluate_knockouts(jd_text: str, cv_data: dict, user_prefs: dict | None = None) -> KnockoutResult:
    """
    Parse hard constraints from the JD and evaluate them against the profile.

    Rules that cannot be evaluated (profile lacks the field) count as PASS —
    the engine never punishes missing data with a knockout. Only explicit,
    provable conflicts fail. Title mismatch and overqualification are
    deliberately NOT knockout criteria (Principle 3).
    """
    prefs = user_prefs or {}
    rules: list[KnockoutRule] = []
    reasons: list[str] = []

    # Work model: only fails when JD says on-site-only AND the user has an
    # explicit remote-only preference on record.
    if _WORK_MODEL_RE.search(jd_text):
        user_remote_only = prefs.get("work_model") == "remote_only"
        passed = not user_remote_only
        rules.append(KnockoutRule(kind="work_model", requirement="On-site only", passed=passed))
        if not passed:
            reasons.append("JD requires on-site only; profile preference is remote-only.")

    # Minimum years: fails only when candidate total is BELOW the stated minimum.
    m = _MIN_YEARS_RE.search(jd_text)
    if m:
        required = float(m.group(1))
        have = _total_experience_years(cv_data)
        # Unknown experience length (0 parsed) → treat as un-evaluable → pass.
        passed = True if have == 0.0 else have >= required
        rules.append(KnockoutRule(kind="min_years", requirement=f"{required:.0f}+ years", passed=passed))
        if not passed:
            reasons.append(f"JD demands {required:.0f}+ years; profile shows {have:.1f}.")

    # Language: evaluable only if the profile stores languages
    # (role_preferences.languages via get_knockout_prefs, or cv_data fallback).
    lang_match = _LANGUAGE_RE.search(jd_text)
    if lang_match:
        needed = lang_match.group(2).lower()
        langs = [str(l).lower() for l in (prefs.get("languages") or cv_data.get("languages", []))]
        passed = True if not langs else any(needed in l for l in langs)
        rules.append(KnockoutRule(kind="language", requirement=f"{lang_match.group(1)} {needed}", passed=passed))
        if not passed:
            reasons.append(f"JD requires {needed}; not listed in profile languages.")

    # Mandatory certification: recorded but never auto-failed — cert synonyms are
    # too varied to prove absence. Surfaced as un-evaluable (passed=None).
    if _CERT_MUST_RE.search(jd_text):
        rules.append(KnockoutRule(kind="certification", requirement="Mandatory certification stated in JD", passed=None))

    failed = any(r.passed is False for r in rules)
    return KnockoutResult(
        rules=rules,
        passed=not failed,
        multiplier=KNOCKOUT_SOFT_FAIL_MULTIPLIER if failed else 1.0,
        reasons=reasons,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Layer 1 — Core competencies vs Confidence Matrix
# ═════════════════════════════════════════════════════════════════════════════

def _normalize(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")


def extract_competencies(structured_jd: "object") -> list[JdCompetency]:
    """
    Build the competency list from a StructuredJd (jd_structure_service).

    requirements[]  → MUST_HAVE
    advantages[]    → NICE_HAVE

    The FULL lists are consumed — no slicing (Principle 1).
    """
    competencies: list[JdCompetency] = []
    for tier, bullets in (
        (CompetencyTier.MUST_HAVE, getattr(structured_jd, "requirements", []) or []),
        (CompetencyTier.NICE_HAVE, getattr(structured_jd, "advantages", []) or []),
    ):
        for bullet in bullets:
            years = None
            m = _MIN_YEARS_RE.search(bullet)
            if m:
                years = float(m.group(1))
            competencies.append(JdCompetency(
                raw_text=bullet.strip(),
                normalized=_normalize(bullet),
                tier=tier,
                min_years=years,
            ))
    return competencies


def _match_entity(comp: JdCompetency, entities: list[dict]) -> Optional[dict]:
    """
    Resolve a JD competency to the best Confidence-Matrix entity.

    Matching is word-boundary based on the entity name inside the requirement
    text (never bare substring — same rule as Principle 2's company matcher).
    Longest entity name wins to prefer specific skills over generic ones.
    """
    text = comp.raw_text.lower()
    best: Optional[dict] = None
    for ent in entities:
        name = str(ent.get("name", "")).lower()
        if not name:
            continue
        pattern = r"\b" + re.escape(name.replace("_", " ")) + r"\b"
        alt     = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, text) or re.search(alt, text):
            if best is None or len(name) > len(str(best.get("name", ""))):
                best = ent
    return best


def score_competencies(
    competencies: list[JdCompetency],
    entity_scores: list[dict],
) -> tuple[float, list[CompetencyMatch], list[str]]:
    """
    Map every JD competency onto the Confidence Matrix and compute the layer score.

    coverage_i = (confidence_score / 100) × verification_multiplier
    layer      = 100 × (0.75 × mean(must coverages) + 0.25 × mean(nice coverages))

    A tier with zero extracted items contributes its full weight via the other
    tier (renormalised) so JDs without an "advantages" section aren't penalised.

    Returns (score 0–100, per-competency detail, unmet must-have gap list).
    """
    matches: list[CompetencyMatch] = []
    for comp in competencies:
        ent = _match_entity(comp, entity_scores)
        if ent is None:
            matches.append(CompetencyMatch(competency=comp))
            continue
        level = str(ent.get("verification_level", "UNVERIFIED"))
        conf  = float(ent.get("score", 0.0))
        mult  = VERIFICATION_MULTIPLIER.get(level, VERIFICATION_MULTIPLIER["UNVERIFIED"])
        matches.append(CompetencyMatch(
            competency=comp,
            matched_entity=str(ent.get("name")),
            confidence_score=round(conf, 1),
            verification_level=level,
            coverage=round((conf / 100.0) * mult, 4),
        ))

    musts = [m for m in matches if m.competency.tier == CompetencyTier.MUST_HAVE]
    nices = [m for m in matches if m.competency.tier == CompetencyTier.NICE_HAVE]

    def _mean(items: list[CompetencyMatch]) -> Optional[float]:
        return sum(m.coverage for m in items) / len(items) if items else None

    must_mean, nice_mean = _mean(musts), _mean(nices)

    if must_mean is None and nice_mean is None:
        score = 0.0
    elif must_mean is None:
        score = 100.0 * nice_mean            # type: ignore[operator]
    elif nice_mean is None:
        score = 100.0 * must_mean
    else:
        score = 100.0 * (W_MUST_HAVE * must_mean + W_NICE_HAVE * nice_mean)

    gaps = [
        f"Must-have not evidenced: {m.competency.raw_text}"
        for m in musts if m.matched_entity is None
    ]
    return round(score, 1), matches, gaps


# ═════════════════════════════════════════════════════════════════════════════
# Layer 2 — Impact & Scale density
# ═════════════════════════════════════════════════════════════════════════════

# Quantified-scale signal patterns, ordered roughly by recruiter salience.
_SCALE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("monetary",   re.compile(r"[$€₪£]\s?\d[\d,.]*\s*(?:k|m|b|million|billion)?", re.I)),
    ("percentage", re.compile(r"\d{1,3}(?:\.\d+)?\s?%")),
    ("users",      re.compile(r"\b\d[\d,.]*\s*(?:k|m|million|thousand)?\+?\s*(?:users|customers|clients|accounts|subscribers|MAU|DAU)\b", re.I)),
    ("team",       re.compile(r"\b(?:led|managed|built|grew)\b.{0,30}?\b(?:team|group)s?\s+of\s+\d+", re.I)),
    ("throughput", re.compile(r"\b\d[\d,.]*\s*(?:requests|events|transactions|jobs|tickets|deals)\s*(?:/|per)\s*(?:sec|second|min|minute|day|month)\b", re.I)),
    ("multi_region", re.compile(r"\b(?:multi[- ]region|global(?:ly)?|\d+\s+(?:countries|markets|regions))\b", re.I)),
]

_JD_SCALE_DEMAND = re.compile(
    r"\b(?:scale|high[- ]volume|enterprise|millions? of|global|multi[- ]region|"
    r"large (?:team|org)|\d[\d,.]*\s*(?:users|customers|requests))\b", re.I,
)


def score_impact_density(cv_data: dict, jd_text: str) -> ImpactDensityResult:
    """
    Extract quantified scale signals from the FULL experience history
    (no slicing — Principle 1) and score density against the JD's demands.

    Scoring:
      base   = min(distinct signal kinds × 18, 72)     — breadth of evidence
      volume = min(total signal count × 4, 28)         — depth of evidence
      score  = base + volume  (0–100)
    When the JD itself states scale demands, an unmet-breadth haircut is NOT
    applied — absence of numbers is already reflected in a low base. The JD
    demands are returned for the gap report only.
    """
    texts: list[str] = []
    for exp in cv_data.get("experience", []):
        for key in ("description", "summary", "highlights", "bullets"):
            v = exp.get(key)
            if isinstance(v, str):
                texts.append(v)
            elif isinstance(v, list):
                texts.extend(str(x) for x in v)
    corpus = "\n".join(texts)

    signals: list[str] = []
    kinds:   set[str]  = set()
    for kind, pat in _SCALE_PATTERNS:
        found = pat.findall(corpus)
        if found:
            kinds.add(kind)
            signals.extend(str(f).strip() for f in found)

    demands = [m.group(0) for m in _JD_SCALE_DEMAND.finditer(jd_text)]

    base   = min(len(kinds) * 18.0, 72.0)
    volume = min(len(signals) * 4.0, 28.0)
    return ImpactDensityResult(
        candidate_signals=signals[:50],   # display cap only; scoring used full set
        jd_scale_demands=demands[:20],
        score=round(base + volume, 1),
    )


# ═════════════════════════════════════════════════════════════════════════════
# Final composition
# ═════════════════════════════════════════════════════════════════════════════

def compute_ats_match(
    jd_text:        str,
    structured_jd:  "object",
    cv_data:        dict,
    entity_scores:  list[dict],
    local_score:    float,
    target_company: str = "",
    user_prefs:     dict | None = None,
) -> AtsMatchResult:
    """
    Full three-layer ATS match. Pure and deterministic — no LLM call.

    Raises ThinJdError when the JD is under the minimum length so the caller
    keeps the existing Principle-4 fallback (composite = 0.30 × local).
    """
    if len(jd_text.strip()) < _MIN_JD_CHARS:
        raise ThinJdError(
            f"JD has {len(jd_text.strip())} chars (<{_MIN_JD_CHARS}); "
            "caller must use the 0.30 × local fallback."
        )

    knockout = evaluate_knockouts(jd_text, cv_data, user_prefs)

    competencies = extract_competencies(structured_jd)
    comp_score, comp_detail, gaps = score_competencies(competencies, entity_scores)

    # Principle 2 — company legacy floor (word-boundary matching lives in
    # match_score_service._find_prior_employer; imported to avoid duplication).
    legacy: Optional[str] = None
    if target_company:
        from backend.services.match_score_service import _find_prior_employer
        legacy = _find_prior_employer(cv_data, target_company)
        if legacy:
            comp_score = max(comp_score, COMPANY_LEGACY_COMPETENCY_FLOOR)

    impact = score_impact_density(cv_data, jd_text)

    composite = (
        W_COMPETENCY * comp_score
        + W_IMPACT   * impact.score
        + W_LOCAL    * max(0.0, min(local_score, 100.0))
    )
    final = round(knockout.multiplier * composite, 1)

    return AtsMatchResult(
        final_score=final,
        base_score=round(composite, 1),
        knockout=knockout,
        competency_score=round(comp_score, 1),
        competency_detail=comp_detail,
        impact=impact,
        local_score=round(local_score, 1),
        legacy_company=legacy,
        gap_analysis=gaps,
    )
