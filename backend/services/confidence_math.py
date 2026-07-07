"""
confidence_math.py — Active Confidence Matrix scoring functions.

Design invariants
-----------------
1. Score is ALWAYS recomputed from the full evidence ledger — never
   accumulated in place.  This means any evidence correction propagates
   automatically on the next recompute call.

2. Freshness decay is exponential (half-life model), not linear.  A skill
   proved 30 days ago retains most of its weight; one proved 3 years ago
   approaches a floor value but never fully disappears.

3. Source-type caps prevent a flood of low-weight evidence from outweighing
   a single high-quality STAR event.  Two separate cap tables govern positive
   and negative evidence independently.

4. The geometric combination formula ensures that multi-source positive
   evidence scores higher than any single source alone, with diminishing
   returns per additional source.

5. Negative evidence (flags, contradictions) is handled separately:
   penalty = Σ(|weight| × freshness), capped at NEGATIVE_PENALTY_CAP_RATIO
   of the positive score.  This prevents a single bad session from zeroing out
   years of accumulated evidence.

6. Final score is always clamped to [0.0, 100.0].

Source-type taxonomy
--------------------
Architecture bucket (evidence of capability at design/system level):
  self_assertion           10–25 pts   User stated it in chat/onboarding
  cv_parse                 20–30 pts   NLP extraction from uploaded CV
  contextual_reinforcement 15–20 pts   Skill mentioned across sessions unprompted
  certification            40–60 pts   Document-backed proof (cert, diploma)
  portfolio                45–65 pts   Artifact / case study
  conversation_star        65–90 pts   Ariel STAR probe passed (scaled by confidence)

Syntax bucket (evidence of manual execution, no AI assist):
  manual_assessment        70–90 pts   Whiteboard test, quiz, or non-AI coding sample
                                       administered by Ariel or submitted by the user.

Negative sources (base_weight < 0, stored as negative floats):
  negative_flag           −15 to −30  Contradiction or shallow STAR response

Decoupled scoring formula
-------------------------
  Architecture_Confidence: scored from the architecture bucket only
  Syntax_Confidence:       scored from the syntax (manual_assessment) bucket only

  Final blended score:
    If Syntax_Confidence == 0 → cap = min(Architecture_Confidence × 0.4, 30.0)
    Otherwise                 → Architecture_Confidence × 0.4 + Syntax_Confidence × 0.6

  Rationale: a skill only demonstrated through AI-assisted projects or high-level
  design discussions is honest at the architecture level but unverified for
  individual syntax execution.  The 30-point ceiling signals exactly this gap to
  the recruiter and the candidate, without erasing the real architecture capability.

Verification levels
-------------------
  VERIFIED_MANUAL      Has manual_assessment evidence (syntax_confidence > 0)
  ORCHESTRATION_ONLY   Has architecture evidence but no manual verification
  UNVERIFIED           No meaningful evidence on either dimension

Usage
-----
    from backend.services.confidence_math import (
        compute_confidence_score, compute_decoupled_score, EvidenceRow, DecoupledScore
    )

    rows: list[EvidenceRow] = [...]   # fetched from evidence_records table
    score  = compute_confidence_score(rows)     # legacy blended score (backwards compat)
    dscore = compute_decoupled_score(rows)      # new truth-based split
    status = verification_status(score)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypedDict


# ── Positive source configuration ─────────────────────────────────────────────

# Maximum contribution any one source *type* can make to the positive score.
# Multiple records of the same type are summed before the cap is applied.
SOURCE_CAPS: dict[str, float] = {
    "self_assertion":          20.0,
    "cv_parse":                30.0,
    "contextual_reinforcement":40.0,   # up to 2 sessions × 20 pts before diminishing
    "certification":           55.0,
    "portfolio":               60.0,
    "conversation_star":       90.0,
    # Syntax bucket — manual execution, no AI assist
    "manual_assessment":       90.0,   # single passing whiteboard/quiz can near-fully verify
}

# Default base weights written to evidence_records by ProfileUpdateService.
# conversation_star is scaled further by extraction_confidence at write time.
BASE_WEIGHTS: dict[str, float] = {
    "self_assertion":          15.0,
    "cv_parse":                25.0,
    "contextual_reinforcement":20.0,
    "certification":           55.0,
    "portfolio":               50.0,
    "conversation_star":       80.0,
    # Syntax bucket
    "manual_assessment":       85.0,   # gold standard — written/executed without AI
    # Negative — stored as a negative float in the DB
    "negative_flag":          -25.0,
}

# ── Negative source configuration ─────────────────────────────────────────────

# Maximum total penalty a negative source type can apply.
# All negative records are summed; the result is capped here before subtraction.
NEGATIVE_SOURCE_CAPS: dict[str, float] = {
    "negative_flag": 50.0,   # one severe flag can remove up to 50 pts
}

# Safety floor: penalty cannot exceed this fraction of the positive score.
# Ensures a single bad session never zeros out years of accumulated evidence.
NEGATIVE_PENALTY_CAP_RATIO: float = 0.80

# ── Decay half-lives ──────────────────────────────────────────────────────────

# After this many days, a piece of evidence contributes half its original weight.
HALF_LIFE_DAYS: dict[str, float] = {
    "self_assertion":           90.0,   # user assertions decay fast
    "cv_parse":                730.0,   # 2 years — CV mentions age slowly
    "contextual_reinforcement":180.0,   # 6 months — reinforcement fades if not refreshed
    "certification":          1095.0,   # 3 years
    "portfolio":               730.0,   # 2 years
    "conversation_star":       365.0,   # 1 year — even behavioral proof ages
    "manual_assessment":       730.0,   # 2 years — manual proof is durable
    "negative_flag":           180.0,   # flags decay in 6 months; fresh evidence can recover
}

# ── Evidence bucket routing ────────────────────────────────────────────────────
# source_types routed to the syntax bucket (manual execution, no AI).
# All other positive source_types go to the architecture bucket.
SYNTAX_SOURCE_TYPES: frozenset[str] = frozenset({"manual_assessment"})

# ── Decoupled scoring constants ───────────────────────────────────────────────

# Blending weights for the final score when syntax evidence exists.
ARCH_WEIGHT:   float = 0.40
SYNTAX_WEIGHT: float = 0.60

# Dynamic Evidence Multiplier — replaces the static VERIFICATION_RISK_FACTOR.
#
# Base (no qualifying engagement):  0.5
# Per STAR probe or Whiteboard Challenge completed:  +0.1 (up to max 1.0)
# VERIFIED_MANUAL (has manual_assessment evidence):  always 1.0
#
# Qualifying event source types: 'conversation_star', 'manual_assessment'
EVIDENCE_MULTIPLIER_BASE:  float = 0.50
EVIDENCE_MULTIPLIER_STEP:  float = 0.10
EVIDENCE_MULTIPLIER_MAX:   float = 1.00
QUALIFYING_EVENT_TYPES: frozenset[str] = frozenset({"conversation_star", "manual_assessment"})

# Legacy static table kept for the backfill script — not used in live scoring.
VERIFICATION_RISK_FACTOR: dict[str, float] = {
    "VERIFIED_MANUAL":    1.00,
    "ORCHESTRATION_ONLY": 0.50,
    "UNVERIFIED":         0.50,
}

# Syntax Recovery thresholds:
# When architecture_confidence exceeds this value AND total positive evidence
# count meets the minimum, auto-set syntax_confidence to 50% of arch score.
SYNTAX_RECOVERY_ARCH_THRESHOLD:    float = 70.0
SYNTAX_RECOVERY_MIN_EVIDENCE:      int   = 3
SYNTAX_RECOVERY_RATIO:             float = 0.50

# Verification level thresholds
VL_VERIFIED_MANUAL_THRESHOLD:    float = 1.0    # any syntax evidence
VL_ORCHESTRATION_ONLY_THRESHOLD: float = 10.0   # any meaningful architecture evidence

# ── Status thresholds ─────────────────────────────────────────────────────────

VERIFICATION_THRESHOLDS: dict[str, float] = {
    "verified":       75.0,
    "partial":        45.0,
    "needs_evidence": 20.0,
    # below needs_evidence → 'unverified'
}

# Below this final score, ProfileUpdateService sets manual_review_required = True.
# 25.0 = 50% risk factor × a raw score of 50 — the meaningful floor for "needs attention".
MANUAL_REVIEW_THRESHOLD: float = 25.0


# ── Type alias ────────────────────────────────────────────────────────────────

class EvidenceRow(TypedDict):
    """One row from evidence_records, normalised for the scoring function."""
    source_type:    str      # key into SOURCE_CAPS / NEGATIVE_SOURCE_CAPS
    base_weight:    float    # positive OR negative float, as stored in the DB
    verified_at:    datetime
    is_ai_assisted: bool     # True → AI wrote boilerplate, human orchestrated


# When evidence is tagged ai_assisted, the effective weight is reduced by this
# multiplier before the freshness and cap calculations run.
# 0.35 means AI-augmented evidence contributes only 35% of what direct mastery would.
AI_AUGMENTATION_PENALTY: float = 0.35


# ── Decoupled score result ────────────────────────────────────────────────────

@dataclass(frozen=True)
class DecoupledScore:
    """
    Truth-based dual-dimension score for a single profile entity.

    architecture_confidence : 0–100  scored from all non-manual_assessment evidence
    syntax_confidence       : 0–100  scored from manual_assessment evidence only
    final_score             : 0–100  the blended, capped result used for storage
    verification_level      : str    VERIFIED_MANUAL | ORCHESTRATION_ONLY | UNVERIFIED
    evidence_multiplier     : float  dynamic risk weight (0.5 base + 0.1/qualifying event)
    evidence_count          : int    total positive evidence records
    """
    architecture_confidence: float
    syntax_confidence:       float
    final_score:             float
    verification_level:      str
    evidence_multiplier:     float = EVIDENCE_MULTIPLIER_BASE
    evidence_count:          int   = 0


def _geo_combine(contributions: list[float]) -> float:
    """Geometric combination: 100 × (1 − ∏ (1 − cᵢ/100))."""
    complement = 1.0
    for c in contributions:
        complement *= 1.0 - (c / 100.0)
    return 100.0 * (1.0 - complement)


def geo_combine(contributions: list[float]) -> float:
    """
    Public alias of `_geo_combine` for callers outside this module (e.g.
    ProfileUpdateService.compute_profile_trust_score) that need the same
    monotonic, "more evidence never lowers the score" combination rule.
    """
    return _geo_combine(contributions)


def _positive_score_from_rows(rows: list[EvidenceRow]) -> float:
    """
    Compute the positive evidence score (before negative penalty) for a set of rows.
    Applies AI_AUGMENTATION_PENALTY when is_ai_assisted=True.
    """
    if not rows:
        return 0.0
    by_source: dict[str, float] = {}
    for row in rows:
        stype   = row["source_type"]
        ai_mult = AI_AUGMENTATION_PENALTY if row.get("is_ai_assisted") else 1.0
        weight  = row["base_weight"] * ai_mult * freshness_factor(row["verified_at"], stype)
        by_source[stype] = by_source.get(stype, 0.0) + weight
    contribs = [min(raw, SOURCE_CAPS.get(stype, 100.0)) for stype, raw in by_source.items()]
    return _geo_combine(contribs)


def compute_decoupled_score(evidence_rows: list[EvidenceRow]) -> DecoupledScore:
    """
    Truth-based dual-dimension scoring.

    Splits evidence into two independent buckets:
      Syntax bucket  : source_type == 'manual_assessment'  (no AI, no portfolio)
      Architecture   : everything else (portfolio, STAR, CV, cert, …)

    Formula
    -------
      raw_blended:
          if syntax_confidence > 0:
              raw = architecture_confidence × ARCH_WEIGHT
                    + syntax_confidence     × SYNTAX_WEIGHT
          else:
              raw = architecture_confidence  (unblended — no syntax dimension yet)

      final = raw × VERIFICATION_RISK_FACTOR[verification_level]
          VERIFIED_MANUAL    → ×1.00  (full score)
          ORCHESTRATION_ONLY → ×0.50  (pending manual validation)
          UNVERIFIED         → ×0.50  (pending manual validation)

      This means an 80-point STAR-only skill returns 40.0 — "pending validation",
      not zero.  The raw_blended score is stored as architecture_confidence so
      recruiters and the UI can always see the full potential vs. the validated score.

    Negative flags penalise the architecture bucket only (they come from
    behavioural contradictions, not from failed manual tests).

    Parameters
    ----------
    evidence_rows : list[EvidenceRow]
        All non-hard-expired evidence for this entity.

    Returns
    -------
    DecoupledScore
    """
    if not evidence_rows:
        return DecoupledScore(
            architecture_confidence=0.0,
            syntax_confidence=0.0,
            final_score=0.0,
            verification_level="UNVERIFIED",
            evidence_multiplier=EVIDENCE_MULTIPLIER_BASE,
            evidence_count=0,
        )

    pos_rows = [r for r in evidence_rows if r["base_weight"] >= 0]
    neg_rows = [r for r in evidence_rows if r["base_weight"] <  0]

    syntax_rows = [r for r in pos_rows if r["source_type"] in SYNTAX_SOURCE_TYPES]
    arch_rows   = [r for r in pos_rows if r["source_type"] not in SYNTAX_SOURCE_TYPES]

    # ── Architecture score (with negative penalty) ────────────────────────────
    arch_pos = _positive_score_from_rows(arch_rows)

    neg_by_source: dict[str, float] = {}
    for row in neg_rows:
        stype  = row["source_type"]
        weight = abs(row["base_weight"]) * freshness_factor(row["verified_at"], stype)
        neg_by_source[stype] = neg_by_source.get(stype, 0.0) + weight
    raw_penalty = sum(
        min(raw, NEGATIVE_SOURCE_CAPS.get(stype, 50.0))
        for stype, raw in neg_by_source.items()
    )
    penalty = min(raw_penalty, arch_pos * NEGATIVE_PENALTY_CAP_RATIO)
    arch_score = round(min(max(arch_pos - penalty, 0.0), 100.0), 1)

    # ── Syntax score ──────────────────────────────────────────────────────────
    syntax_score = round(min(max(_positive_score_from_rows(syntax_rows), 0.0), 100.0), 1)

    # ── Qualifying (AI-verified) evidence count ───────────────────────────────
    # Only conversation_star (Ariel STAR probe passed) and manual_assessment
    # (Whiteboard Challenge) count as AI-verified engagement events.
    # Raw uploads (cv_parse, portfolio) and chat mentions do NOT count —
    # those are ingested automatically without an AI approval decision.
    # Failed probes are stored as negative_flag (base_weight < 0) and are
    # already excluded from pos_rows, so no additional filter is needed.
    qualifying_count = sum(
        1 for r in pos_rows if r["source_type"] in QUALIFYING_EVENT_TYPES
    )

    # ── Syntax recovery — deep AI-verified engagement implies syntax competence ─
    # Requires arch > threshold AND ≥ N AI-verified events (not raw uploads).
    # A CV parse alone, no matter how strong, cannot trigger recovery.
    if (
        syntax_score == 0.0
        and arch_score > SYNTAX_RECOVERY_ARCH_THRESHOLD
        and qualifying_count >= SYNTAX_RECOVERY_MIN_EVIDENCE
    ):
        syntax_score = round(arch_score * SYNTAX_RECOVERY_RATIO, 1)

    # ── Raw blended score ─────────────────────────────────────────────────────
    if syntax_score > 0.0:
        raw_blended = round(
            min(arch_score * ARCH_WEIGHT + syntax_score * SYNTAX_WEIGHT, 100.0), 1
        )
    else:
        # No syntax evidence yet — raw score is the architecture score alone.
        # The dynamic multiplier will discount it below.
        raw_blended = arch_score

    # ── Verification level ────────────────────────────────────────────────────
    if syntax_score >= VL_VERIFIED_MANUAL_THRESHOLD:
        vl = "VERIFIED_MANUAL"
    elif arch_score >= VL_ORCHESTRATION_ONLY_THRESHOLD:
        vl = "ORCHESTRATION_ONLY"
    else:
        vl = "UNVERIFIED"

    # ── Dynamic evidence multiplier ───────────────────────────────────────────
    # VERIFIED_MANUAL always gets full weight (1.0).
    # For all other levels: start at 0.5, +0.1 per AI-verified qualifying event,
    # capped at 1.0.  Raw uploads and chat mentions do NOT move this needle.
    if vl == "VERIFIED_MANUAL":
        multiplier = EVIDENCE_MULTIPLIER_MAX
    else:
        multiplier = round(
            min(EVIDENCE_MULTIPLIER_BASE + EVIDENCE_MULTIPLIER_STEP * qualifying_count,
                EVIDENCE_MULTIPLIER_MAX),
            2,
        )

    final = round(min(raw_blended * multiplier, 100.0), 1)

    return DecoupledScore(
        architecture_confidence=arch_score,
        syntax_confidence=syntax_score,
        final_score=final,
        verification_level=vl,
        evidence_multiplier=multiplier,
        evidence_count=qualifying_count,   # UI shows AI-verified count, not raw uploads
    )


# ── Core math ─────────────────────────────────────────────────────────────────

def freshness_factor(verified_at: datetime, source_type: str) -> float:
    """
    Exponential decay: factor = 2^(−age_days / half_life_days).

    Returns 1.0 for brand-new evidence, approaches 0.0 asymptotically.
    Never returns exactly 0.0 — even ancient evidence leaves a trace.

    Parameters
    ----------
    verified_at : datetime
        When the evidence was recorded.  Naïve datetimes are treated as UTC.
    source_type : str
        Controls the half-life via HALF_LIFE_DAYS.  Unknown types default to 365.
    """
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    now       = datetime.now(timezone.utc)
    age_days  = max(0.0, (now - verified_at).total_seconds() / 86_400)
    half_life = HALF_LIFE_DAYS.get(source_type, 365.0)
    return math.pow(2.0, -age_days / half_life)


def compute_confidence_score(evidence_rows: list[EvidenceRow]) -> float:
    """
    Recompute the confidence score for a single profile entity.

    Algorithm
    ---------
    Phase A — Positive evidence:
        1. Split rows by source_type, summing (base_weight × freshness_factor).
        2. Cap each source type at SOURCE_CAPS[type].
        3. Geometric combination:  score = 100 × (1 − ∏ᵢ (1 − cᵢ / 100))
           This gives diminishing returns — a second strong source adds value
           but cannot double the score.

    Phase B — Negative evidence:
        1. For each negative-flag row, accumulate |base_weight| × freshness.
        2. Cap the total penalty per flag type at NEGATIVE_SOURCE_CAPS[type].
        3. Apply a safety floor: penalty ≤ NEGATIVE_PENALTY_CAP_RATIO × positive_score.
           This means even the worst possible flags cannot zero out a well-verified skill.
        4. final = positive_score − penalty

    Parameters
    ----------
    evidence_rows : list[EvidenceRow]
        All non-hard-expired evidence for this entity.  Pass an empty list
        to receive 0.0.

    Returns
    -------
    float   Confidence score in [0.0, 100.0], 1 decimal place.
    """
    if not evidence_rows:
        return 0.0

    # ── Phase A: positive evidence ───────────────────────────────────────────
    positive_rows = [r for r in evidence_rows if r["base_weight"] >= 0]
    negative_rows = [r for r in evidence_rows if r["base_weight"] <  0]

    positive_score = _positive_score_from_rows(positive_rows)

    if not negative_rows:
        return round(min(max(positive_score, 0.0), 100.0), 1)

    # ── Phase B: negative evidence ───────────────────────────────────────────
    # Group by source_type so that each flag type is independently capped.
    neg_by_source: dict[str, float] = {}
    for row in negative_rows:
        stype  = row["source_type"]
        # base_weight is already negative; take the absolute value for accumulation
        weight = abs(row["base_weight"]) * freshness_factor(row["verified_at"], stype)
        neg_by_source[stype] = neg_by_source.get(stype, 0.0) + weight

    raw_penalty = sum(
        min(raw, NEGATIVE_SOURCE_CAPS.get(stype, 50.0))
        for stype, raw in neg_by_source.items()
    )

    # Safety floor: penalty cannot wipe out more than NEGATIVE_PENALTY_CAP_RATIO
    # of the positive score.  Even a badly flagged skill retains some signal.
    max_allowed_penalty = positive_score * NEGATIVE_PENALTY_CAP_RATIO
    penalty = min(raw_penalty, max_allowed_penalty)

    final = positive_score - penalty
    return round(min(max(final, 0.0), 100.0), 1)


def verification_status(score: float) -> str:
    """
    Map a confidence score to a human-readable verification tier.

    Note: 'needs_manual_review' is NOT a score-derived status — it is set
    separately as a boolean flag (manual_review_required column) when
    ingest_negative_flag detects a score below MANUAL_REVIEW_THRESHOLD.
    This function only returns the four score-based tiers.

    Tiers
    -----
    verified       ≥ 75  — strong multi-source or STAR-verified
    partial        ≥ 45  — some evidence, gaps remain
    needs_evidence ≥ 20  — entry exists but barely supported
    unverified      < 20 — no meaningful evidence
    """
    if score >= VERIFICATION_THRESHOLDS["verified"]:
        return "verified"
    if score >= VERIFICATION_THRESHOLDS["partial"]:
        return "partial"
    if score >= VERIFICATION_THRESHOLDS["needs_evidence"]:
        return "needs_evidence"
    return "unverified"


def gap_severity(current: float, required: float) -> str:
    """
    Classify how serious a skill gap is for a target job.

    critical — delta > 40 (skill essentially missing)
    moderate — delta 20–40
    minor    — delta < 20 (close, a single session could close it)
    """
    delta = required - current
    if delta > 40:
        return "critical"
    if delta >= 20:
        return "moderate"
    return "minor"
