"""
confidence_matrix_service.py — Four-Category Confidence Matrix

Aggregates profile_entities into four semantic buckets:
  Technical | Product_Leadership | Data_Analysis | Customer_Success

Each entity's raw score is re-weighted by a Source Weight multiplier that
reflects the credibility of the evidence type:

  cv_parse              0.40  — stated on CV, moderate credibility
  portfolio             0.80  — live artifact (JobApply codebase, project)
  conversation_star     0.90  — Ariel STAR-validated behavioral proof
  certification         0.70  — academic / formal cert
  contextual_reinforcement 0.30 — incidental mention across sessions
  self_assertion        0.20  — lowest, unvalidated claim

Recency decay is applied via confidence_math.freshness_factor() (exponential
half-life). Evidence at full age still contributes — it never reaches zero.

Output contract (recharts RadarChart):
  [
    { "category": "Technical",           "value": 78.4 },
    { "category": "Product_Leadership",  "value": 85.1 },
    { "category": "Data_Analysis",       "value": 62.7 },
    { "category": "Customer_Success",    "value": 91.3 },
  ]

Key implementation note
-----------------------
SQLAlchemy text() + SQLite does not expand Python tuples for IN clauses
automatically. We use bindparam(..., expanding=True) which rewrites
  WHERE entity_id IN :ids
into
  WHERE entity_id IN (?, ?, ?, ...)
at execution time with the correct number of placeholders.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from backend.services.confidence_math import AI_AUGMENTATION_PENALTY, freshness_factor

logger = logging.getLogger(__name__)

# ── Source weight multipliers ─────────────────────────────────────────────────

SOURCE_WEIGHT: dict[str, float] = {
    "cv_parse":                0.40,
    "portfolio":               0.80,
    "conversation_star":       0.90,
    "certification":           0.70,
    "contextual_reinforcement": 0.30,
    "self_assertion":          0.20,
}

# Per-source contribution caps (after weight multiplier)
SOURCE_CAP: dict[str, float] = {
    "cv_parse":                12.0,   # 30 × 0.4
    "portfolio":               40.0,   # 50 × 0.8
    "conversation_star":       72.0,   # 80 × 0.9
    "certification":           38.5,   # 55 × 0.7
    "contextual_reinforcement": 12.0,  # 40 × 0.3
    "self_assertion":           3.0,   # 15 × 0.2
}

NEGATIVE_CAP: float = 50.0
PENALTY_CAP_RATIO: float = 0.80

# ── Entity → semantic category mapping ───────────────────────────────────────

ENTITY_CATEGORY_MAP: dict[str, str] = {
    # Technical
    "python":                       "Technical",
    "sql":                          "Technical",
    "react":                        "Technical",
    "javascript":                   "Technical",
    "typescript":                   "Technical",
    "fastapi":                      "Technical",
    "next_js":                      "Technical",
    "nextjs":                       "Technical",
    "html_css":                     "Technical",
    "html":                         "Technical",
    "css":                          "Technical",
    "jira":                         "Technical",
    "figma":                        "Technical",
    "git":                          "Technical",
    "api_development":              "Technical",
    "database_design":              "Technical",
    "sqlite":                       "Technical",
    "postgresql":                   "Technical",
    "supabase":                     "Technical",
    # Product_Leadership
    "product_management":           "Product_Leadership",
    "product_ownership":            "Product_Leadership",
    "sprint_planning":              "Product_Leadership",
    "roadmap_planning":             "Product_Leadership",
    "ux_review":                    "Product_Leadership",
    "user_flow_analysis":           "Product_Leadership",
    "acceptance_criteria":          "Product_Leadership",
    "cross_functional_delivery":    "Product_Leadership",
    "stakeholder_management":       "Product_Leadership",
    "team_leadership":              "Product_Leadership",
    "people_management":            "Product_Leadership",
    "agile_scrum":                  "Product_Leadership",
    "b2b2c_saas":                   "Product_Leadership",
    "product_strategy":             "Product_Leadership",
    "go_to_market":                 "Product_Leadership",
    "user_research":                "Product_Leadership",
    # Data_Analysis
    "data_analysis":                "Data_Analysis",
    "power_bi":                     "Data_Analysis",
    "powerbi":                      "Data_Analysis",
    "dax":                          "Data_Analysis",
    "excel":                        "Data_Analysis",
    "excel_vba":                    "Data_Analysis",
    "machine_learning":             "Data_Analysis",
    "a_b_testing":                  "Data_Analysis",
    "data_visualization":           "Data_Analysis",
    "kpi_design":                   "Data_Analysis",
    "funnel_analysis":              "Data_Analysis",
    "retention_analysis":           "Data_Analysis",
    "etl":                          "Data_Analysis",
    "data_driven_decision_making":  "Data_Analysis",
    "sql_reporting":                "Data_Analysis",
    # Customer_Success
    "customer_success":             "Customer_Success",
    "account_management":           "Customer_Success",
    "b2b_relationships":            "Customer_Success",
    "client_retention":             "Customer_Success",
    "onboarding":                   "Customer_Success",
    "escalation_management":        "Customer_Success",
    "live_event_operations":        "Customer_Success",
    "insurance_domain":             "Customer_Success",
    "pension_migrations":           "Customer_Success",
    "saas_migrations":              "Customer_Success",
    "renewal_ownership":            "Customer_Success",
    "upsell":                       "Customer_Success",
    "churn_prevention":             "Customer_Success",
    "global_account_management":    "Customer_Success",
    "partner_management":           "Customer_Success",
}

_TYPE_FALLBACK: dict[str, str] = {
    "skill":      "Technical",
    "domain":     "Customer_Success",
    "experience": "Product_Leadership",
    "trait":      "Product_Leadership",
}

CATEGORIES: list[str] = [
    "Technical",
    "Product_Leadership",
    "Data_Analysis",
    "Customer_Success",
]


# ── TypedDicts ────────────────────────────────────────────────────────────────

class RadarDatum(TypedDict):
    category:   str
    value:      float   # final blended score (stored confidence_score)
    arch_value: float   # Architecture_Confidence average for the category
    syn_value:  float   # Syntax_Confidence average for the category


class EntityScore(TypedDict):
    entity_id:               str
    name:                    str
    category:                str
    score:                   float
    architecture_confidence: float
    syntax_confidence:       float
    verification_level:      str
    skill_tier:              str | None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_category(normalized_name: str, entity_type: str) -> str:
    if normalized_name in ENTITY_CATEGORY_MAP:
        return ENTITY_CATEGORY_MAP[normalized_name]
    for key, cat in ENTITY_CATEGORY_MAP.items():
        if key in normalized_name or normalized_name in key:
            return cat
    return _TYPE_FALLBACK.get(entity_type, "Technical")


def _compute_weighted_score(evidence_rows: list[dict], entity_name: str = "") -> float:
    """
    Geometric combination of source-weighted, decay-adjusted evidence.

    Positive phase:
      1. For each source_type bucket: sum(base_weight × SOURCE_WEIGHT × freshness)
      2. Cap each bucket at SOURCE_CAP[source_type]
      3. Geometric: score = 100 × (1 − ∏(1 − capped_i / 100))

    Negative phase:
      penalty = Σ(|base_weight| × freshness), capped at NEGATIVE_CAP per type
      and at PENALTY_CAP_RATIO × positive_score overall.
    """
    if not evidence_rows:
        return 0.0

    pos_rows = [r for r in evidence_rows if r["base_weight"] >= 0]
    neg_rows = [r for r in evidence_rows if r["base_weight"] < 0]

    pos_by_source: dict[str, float] = {}
    for r in pos_rows:
        stype   = r["source_type"]
        decay   = freshness_factor(r["verified_at"], stype)
        src_wt  = SOURCE_WEIGHT.get(stype, 0.25)
        ai_mult = AI_AUGMENTATION_PENALTY if r.get("is_ai_assisted") else 1.0
        weight  = r["base_weight"] * src_wt * ai_mult * decay
        pos_by_source[stype] = pos_by_source.get(stype, 0.0) + weight

    contributions = [
        min(raw, SOURCE_CAP.get(stype, 30.0))
        for stype, raw in pos_by_source.items()
    ]

    complement = 1.0
    for c in contributions:
        complement *= 1.0 - (c / 100.0)
    positive_score = 100.0 * (1.0 - complement)

    logger.debug(
        "[confidence_matrix] entity=%r  sources=%s  contributions=%s  positive=%.1f",
        entity_name,
        {k: round(v, 2) for k, v in pos_by_source.items()},
        [round(c, 2) for c in contributions],
        positive_score,
    )

    if not neg_rows:
        return round(min(max(positive_score, 0.0), 100.0), 1)

    neg_by_source: dict[str, float] = {}
    for r in neg_rows:
        stype  = r["source_type"]
        decay  = freshness_factor(r["verified_at"], stype)
        neg_by_source[stype] = neg_by_source.get(stype, 0.0) + abs(r["base_weight"]) * decay

    raw_penalty = sum(min(v, NEGATIVE_CAP) for v in neg_by_source.values())
    penalty = min(raw_penalty, positive_score * PENALTY_CAP_RATIO)
    final = round(min(max(positive_score - penalty, 0.0), 100.0), 1)

    logger.debug("[confidence_matrix] entity=%r  penalty=%.1f  final=%.1f", entity_name, penalty, final)
    return final


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _fetch_evidence(conn, entity_ids: list[str]) -> dict[str, list[dict]]:
    """
    Fetch all non-expired evidence rows for the given entity_ids.

    Uses bindparam(expanding=True) so SQLAlchemy correctly expands the list
    into individual IN-clause placeholders for SQLite:
      WHERE entity_id IN (?, ?, ?)
    rather than the broken  WHERE entity_id IN ?  form.
    """
    if not entity_ids:
        return {}

    now_iso = datetime.now(timezone.utc).isoformat()

    stmt = text("""
        SELECT entity_id, source_type, base_weight, verified_at, is_ai_assisted
        FROM   evidence_records
        WHERE  entity_id IN :ids
          AND  (hard_expires_at IS NULL OR hard_expires_at > :now)
    """).bindparams(bindparam("ids", expanding=True))

    rows = conn.execute(stmt, {"ids": entity_ids, "now": now_iso}).fetchall()

    result: dict[str, list[dict]] = {eid: [] for eid in entity_ids}
    for row in rows:
        eid = row[0]
        if eid in result:
            result[eid].append({
                "source_type":    row[1],
                "base_weight":    float(row[2]),
                "verified_at":    _parse_dt(row[3]),
                "is_ai_assisted": bool(row[4]) if row[4] is not None else False,
            })

    logger.debug(
        "[confidence_matrix] fetched %d evidence rows for %d entities",
        len(rows), len(entity_ids),
    )
    return result


# ── Public API ────────────────────────────────────────────────────────────────

def get_confidence_matrix(user_id: str, engine: Engine) -> list[RadarDatum]:
    """
    Compute the four-category Confidence Matrix for `user_id`.

    Every category is always present in the output with value ≥ 0.0 so that
    recharts RadarChart renders all four axes even when some have no evidence.
    """
    with engine.connect() as conn:
        entity_rows = conn.execute(
            text("""
                SELECT entity_id, entity_type, normalized_name, confidence_score,
                       architecture_confidence, syntax_confidence
                FROM   profile_entities
                WHERE  user_id = :uid
            """),
            {"uid": user_id},
        ).fetchall()

    if not entity_rows:
        logger.warning("[confidence_matrix] no entities found for user_id=%s", user_id)
        return [{"category": c, "value": 0.0, "arch_value": 0.0, "syn_value": 0.0}
                for c in CATEGORIES]

    entity_ids = [r[0] for r in entity_rows]
    logger.info(
        "[confidence_matrix] user=%s  entity_count=%d", user_id, len(entity_ids)
    )

    with engine.connect() as conn:
        evidence_by_entity = _fetch_evidence(conn, entity_ids)

    cat_scores: dict[str, list[float]] = {c: [] for c in CATEGORIES}
    cat_arch:   dict[str, list[float]] = {c: [] for c in CATEGORIES}
    cat_syn:    dict[str, list[float]] = {c: [] for c in CATEGORIES}

    for row in entity_rows:
        entity_id, entity_type, normalized_name, fallback_score, arch_col, syn_col = row
        evidence = evidence_by_entity.get(entity_id, [])
        score = (
            _compute_weighted_score(evidence, entity_name=normalized_name or entity_id)
            if evidence
            else float(fallback_score or 0.0)
        )
        cat = _resolve_category(normalized_name or "", entity_type or "skill")
        cat_scores[cat].append(score)
        cat_arch[cat].append(float(arch_col or 0.0))
        cat_syn[cat].append(float(syn_col  or 0.0))
        logger.debug(
            "[confidence_matrix] entity=%r  cat=%s  ev=%d  score=%.1f  arch=%.1f  syn=%.1f",
            normalized_name, cat, len(evidence), score,
            float(arch_col or 0.0), float(syn_col or 0.0),
        )

    def _avg(scores: list[float]) -> float:
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    result = [
        {
            "category":   cat,
            "value":      _avg(cat_scores[cat]),
            "arch_value": _avg(cat_arch[cat]),
            "syn_value":  _avg(cat_syn[cat]),
        }
        for cat in CATEGORIES
    ]

    logger.info("[confidence_matrix] result for user=%s: %s", user_id, result)
    return result


def get_entity_breakdown(user_id: str, engine: Engine) -> list[EntityScore]:
    """
    Per-entity scores with resolved category — used for RadarChart axis tooltips.
    Always returns a list (empty when the user has no entities).
    """
    with engine.connect() as conn:
        entity_rows = conn.execute(
            text("""
                SELECT entity_id, name, entity_type, normalized_name,
                       skill_tier, architecture_confidence,
                       syntax_confidence, verification_level
                FROM   profile_entities
                WHERE  user_id = :uid
                ORDER  BY name
            """),
            {"uid": user_id},
        ).fetchall()

    if not entity_rows:
        return []

    entity_ids = [r[0] for r in entity_rows]

    with engine.connect() as conn:
        evidence_by_entity = _fetch_evidence(conn, entity_ids)

    result: list[EntityScore] = []
    for row in entity_rows:
        (entity_id, name, entity_type, normalized_name,
         skill_tier, arch_conf, syn_conf, vl) = row
        evidence = evidence_by_entity.get(entity_id, [])
        score = (
            _compute_weighted_score(evidence, entity_name=name)
            if evidence
            else 0.0
        )
        cat = _resolve_category(normalized_name or "", entity_type or "skill")
        result.append({
            "entity_id":               entity_id,
            "name":                    name,
            "category":                cat,
            "score":                   score,
            "architecture_confidence": float(arch_conf or 0.0),
            "syntax_confidence":       float(syn_conf  or 0.0),
            "verification_level":      vl or "UNVERIFIED",
            "skill_tier":              skill_tier,
        })

    return result
