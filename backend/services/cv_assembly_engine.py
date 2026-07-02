"""
Zero-Hallucination CV Assembly Engine.

Consumes the gap analysis from ats_match_engine.AtsMatchResult and assembles a
tailored CV using ONLY verified facts from the candidate's base data. The LLM
(when used at all) is a *phrasing* layer, never a *fact* layer: every generated
bullet is validated against its source facts, and any bullet containing a
number, company, or named entity that does not trace back to a fact is
REJECTED and replaced with the deterministic fallback rendering.

Bullet grammar (rigidly enforced):
    [Action] + [Context/Complexity] + [Impact/Metric]

Fact provenance model:
    VerifiedFact  — one atomic, evidence-backed claim (from CV parse, STAR
                    conversation, portfolio, certification). Each fact carries
                    its source and the raw literal strings (numbers, names)
                    it contains.
    BulletDraft   — a candidate bullet with explicit action/context/impact
                    fields, each bound to fact_ids.

Validation invariant:
    tokens_requiring_provenance(bullet_text) ⊆ union(fact.literals)
    Any violation → ValidationError → deterministic fallback.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Data models
# ═════════════════════════════════════════════════════════════════════════════

class VerifiedFact(BaseModel):
    """One atomic evidence-backed claim from the candidate's base data."""
    fact_id:     str
    source_type: str                    # cv_parse | conversation_star | portfolio | certification
    entity:      str                    # confidence-matrix entity this fact evidences
    role:        Optional[str] = None   # job title the fact belongs to
    company:     Optional[str] = None
    action:      str                    # verb phrase, e.g. "Led migration of billing platform"
    context:     Optional[str] = None   # complexity/environment, e.g. "across 3 regulated markets"
    impact:      Optional[str] = None   # metric outcome, e.g. "reducing churn 14%"

    @property
    def literals(self) -> set[str]:
        """All provenance-bearing literal strings this fact contributes."""
        out: set[str] = set()
        for part in (self.action, self.context, self.impact, self.company, self.role):
            if part:
                out.update(_extract_literals(part))
        return out


class BulletDraft(BaseModel):
    """One tailored bullet, bound to the facts that license it."""
    text:      str
    fact_ids:  list[str]
    entity:    str                      # which JD gap/competency this bullet serves
    validated: bool = False


class AssembledCv(BaseModel):
    """Engine output: ordered, provenance-tracked CV content."""
    summary:        str
    bullets:        list[BulletDraft]
    skills:         list[str]                       # only entities with facts behind them
    unserved_gaps:  list[str] = Field(default_factory=list)  # gaps with NO facts — never faked
    rejected_count: int = 0                         # LLM drafts that failed validation


# ═════════════════════════════════════════════════════════════════════════════
# Provenance extraction & validation
# ═════════════════════════════════════════════════════════════════════════════

# Literals that MUST trace to a fact: numbers (with optional % / currency /
# magnitude suffix) and capitalised multi-char proper nouns.
_NUMBER_RE = re.compile(r"[$€₪£]?\d[\d,.]*\s?(?:%|k|m|b|million|billion|thousand)?", re.I)
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}(?:\.[a-z]{2,3})?\b")

# Common sentence-starting words / generic terms that look like proper nouns
# but carry no factual claim.
_PROPER_ALLOWLIST = {
    "Led", "Built", "Managed", "Drove", "Owned", "Delivered", "Launched",
    "Designed", "Improved", "Reduced", "Increased", "Created", "Scaled",
    "The", "This", "Responsible", "Partnered", "Collaborated", "Spearheaded",
    "CV", "KPI", "KPIs", "API", "APIs", "SaaS", "B2B", "B2C", "ATS",
}


def _extract_literals(text: str) -> set[str]:
    """Extract provenance-bearing literals (numbers + proper nouns) from text."""
    out: set[str] = set()
    for m in _NUMBER_RE.finditer(text):
        out.add(re.sub(r"[\s,]", "", m.group(0)).lower())
    for m in _PROPER_RE.finditer(text):
        if m.group(0) not in _PROPER_ALLOWLIST:
            out.add(m.group(0).lower())
    return out


def validate_bullet(text: str, facts: list[VerifiedFact]) -> bool:
    """
    True iff every provenance-bearing literal in `text` appears in the
    union of the source facts' literals. This is the zero-hallucination gate.
    """
    allowed: set[str] = set()
    for f in facts:
        allowed |= f.literals
    required = _extract_literals(text)
    illegal = required - allowed
    if illegal:
        logger.warning("[cv-assembly] bullet rejected — unprovenanced literals: %s", sorted(illegal))
        return False
    return True


# ═════════════════════════════════════════════════════════════════════════════
# Deterministic rendering (the always-safe path)
# ═════════════════════════════════════════════════════════════════════════════

def render_bullet_deterministic(fact: VerifiedFact) -> str:
    """
    Rigid [Action] + [Context/Complexity] + [Impact/Metric] rendering with
    zero generative freedom. Used as the fallback whenever LLM phrasing fails
    validation, and as the default when no LLM is configured.
    """
    parts = [fact.action.rstrip(".")]
    if fact.context:
        parts.append(fact.context.rstrip("."))
    if fact.impact:
        parts.append(fact.impact.rstrip("."))
    return ", ".join(parts) + "."


# ═════════════════════════════════════════════════════════════════════════════
# Fact selection — gap-driven assembly
# ═════════════════════════════════════════════════════════════════════════════

# ── Company-strategy fact bias ────────────────────────────────────────────────
#
# Deterministic, selection-only: a company's financial_vibe re-ranks which
# TRUE facts lead the CV. It cannot create, alter, or reword a fact — the
# validation invariant is untouched. Facts are classified by the metric
# language they already contain.

_EFFICIENCY_FACT_RE = re.compile(
    r"\b(cost|sav(?:e|ed|ing)|reduc|cut|efficien|automat|margin|consolidat|"
    r"streamlin|churn|retention|budget)\b", re.I)
_GROWTH_FACT_RE = re.compile(
    r"\b(grew|grow(?:th|ing)?|scal(?:e|ed|ing)|launch|expand|acquisition|"
    r"new market|revenue|users|adoption|0\s*(?:to|→)\s*1|go[- ]to[- ]market)\b", re.I)

# financial_vibe → regex whose matching facts get ranking priority
_STRATEGY_BIAS: dict[str, re.Pattern] = {
    "lean":        _EFFICIENCY_FACT_RE,
    "turnaround":  _EFFICIENCY_FACT_RE,
    "hypergrowth": _GROWTH_FACT_RE,
    "growth":      _GROWTH_FACT_RE,
    # "stable" / "unknown" → no bias
}


def _fact_matches_strategy(f: VerifiedFact, pattern: re.Pattern) -> bool:
    corpus = " ".join(p for p in (f.action, f.context, f.impact) if p)
    return bool(pattern.search(corpus))


def select_facts_for_gaps(
    facts:          list[VerifiedFact],
    gap_entities:   list[str],
    matched_entities: list[str],
    max_bullets:    int = 12,
    company_vibe:   Optional[str] = None,
) -> tuple[list[VerifiedFact], list[str]]:
    """
    Order facts for the tailored CV:

      1. Facts evidencing entities the JD marked as matched competencies
         (these prove the must-haves — recruiters read these first).
      2. When company_vibe carries a strategy bias: facts whose OWN metric
         language matches the company's current mode (efficiency metrics for
         lean/turnaround, scaling metrics for growth/hypergrowth). Selection
         only — never changes fact content.
      3. Facts with quantified impact (metric present) over those without.
      4. Remaining facts in original (most-recent-first) order.

    Gaps with NO supporting facts are returned in `unserved` — the engine
    NEVER fabricates coverage for them (Zero Hallucination rule). They are
    the caller's signal to prompt the user for real evidence (STAR flow).
    """
    matched_set = {e.lower() for e in matched_entities}
    bias = _STRATEGY_BIAS.get((company_vibe or "").lower())

    def _rank(f: VerifiedFact) -> tuple[int, int, int]:
        primary    = 0 if f.entity.lower() in matched_set else 1
        strategic  = 0 if (bias and _fact_matches_strategy(f, bias)) else 1
        has_metric = 0 if f.impact else 1
        return (primary, strategic, has_metric)

    ordered = sorted(facts, key=_rank)[:max_bullets]

    served = {f.entity.lower() for f in facts}
    unserved = [g for g in gap_entities if g.lower() not in served]
    return ordered, unserved


# ═════════════════════════════════════════════════════════════════════════════
# LLM phrasing layer (optional) — strictly validated
# ═════════════════════════════════════════════════════════════════════════════

_PHRASING_SYSTEM = """\
You rewrite CV bullet points for clarity and impact. You will receive an
Action, a Context, and an Impact string. Combine them into ONE bullet.

ABSOLUTE RULES — violations cause your output to be discarded:
1. Use ONLY the words, numbers, companies, and technologies present in the
   input fields. You may reorder and adjust grammar; you may NOT add any
   number, percentage, company name, product name, or technology.
2. Structure: [Action] + [Context/Complexity] + [Impact/Metric].
3. One line, ≤ 220 characters, no bullet symbol, no quotes.
4. Never inflate: "improved" may not become "dramatically transformed".
Output the bullet text only."""


def phrase_bullet_llm(fact: VerifiedFact, client) -> Optional[str]:
    """
    Ask the LLM to polish one bullet. Returns None on any failure — caller
    falls back to render_bullet_deterministic(). The returned text is NOT
    yet validated; assemble_cv() runs validate_bullet() on it.
    """
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=_PHRASING_SYSTEM,
            messages=[{
                "role": "user",
                "content": (
                    f"Action: {fact.action}\n"
                    f"Context: {fact.context or '(none)'}\n"
                    f"Impact: {fact.impact or '(none)'}"
                ),
            }],
        )
        text = resp.content[0].text.strip()
        return text or None
    except Exception as exc:
        logger.warning("[cv-assembly] LLM phrasing failed (%s) — deterministic fallback", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Fact extraction — evidence_records → VerifiedFact
# ═════════════════════════════════════════════════════════════════════════════

# Clause containing a metric → becomes the Impact slot.
_IMPACT_CLAUSE_RE = re.compile(
    r"((?:reduc|increas|improv|grow|grew|sav|cut|boost|deliver|achiev)\w*\b[^.;]*?"
    r"(?:\d[\d,.]*\s?(?:%|k|m|b|million|billion|thousand)?)[^.;]*)",
    re.I,
)
# Environment/complexity clause → Context slot.
_CONTEXT_CLAUSE_RE = re.compile(
    r"\b(across [^.;]+|for \d[^.;]+|in a [^.;]*(?:environment|team|org)[^.;]*|"
    r"serving [^.;]+|with \d+\s+(?:stakeholders|teams|engineers|markets)[^.;]*)", re.I,
)

# Only positive, human-grounded evidence becomes CV facts. Self-assertions and
# contextual reinforcement are confidence signals, not publishable claims.
_FACT_SOURCE_TYPES = ("cv_parse", "conversation_star", "portfolio", "certification")


def _split_fact_fields(raw: str) -> tuple[str, Optional[str], Optional[str]]:
    """Best-effort split of raw evidence text into (action, context, impact)."""
    text = " ".join(raw.split())          # collapse whitespace
    first = text.split(". ")[0].strip().rstrip(".")

    impact = None
    m = _IMPACT_CLAUSE_RE.search(text)
    if m:
        impact = m.group(1).strip().rstrip(".")

    context = None
    c = _CONTEXT_CLAUSE_RE.search(text)
    if c and (impact is None or c.group(1) not in impact):
        context = c.group(1).strip().rstrip(".")

    # Action = first sentence with any extracted clauses removed from its tail
    action = first
    for clause in (impact, context):
        if clause and clause in action:
            action = action.replace(clause, "").strip(" ,;")
    return (action or first), context, impact


def load_verified_facts(user_id: str, engine) -> list[VerifiedFact]:
    """
    Build the VerifiedFact corpus from the Confidence Matrix's evidence ledger.

    Joins evidence_records → profile_entities for the user, keeps only
    positive-weight rows from fact-grade sources (_FACT_SOURCE_TYPES), newest
    first (Principle 1 ordering), and splits each raw_content into the rigid
    Action / Context / Impact fields.
    """
    from sqlalchemy import bindparam, text as _text

    stmt = _text("""
        SELECT er.evidence_id, er.source_type, er.raw_content,
               pe.name AS entity_name
        FROM evidence_records er
        JOIN profile_entities pe ON pe.entity_id = er.entity_id
        WHERE er.user_id = :uid
          AND er.base_weight > 0
          AND er.source_type IN :stypes
          AND er.raw_content IS NOT NULL
          AND LENGTH(TRIM(er.raw_content)) > 10
        ORDER BY er.verified_at DESC
    """).bindparams(bindparam("stypes", expanding=True))

    with engine.connect() as conn:
        rows = conn.execute(
            stmt, {"uid": user_id, "stypes": list(_FACT_SOURCE_TYPES)}
        ).mappings().all()

    facts: list[VerifiedFact] = []
    for r in rows:
        action, context, impact = _split_fact_fields(str(r["raw_content"]))
        facts.append(VerifiedFact(
            fact_id     = str(r["evidence_id"]),
            source_type = str(r["source_type"]),
            entity      = str(r["entity_name"]),
            action      = action,
            context     = context,
            impact      = impact,
        ))
    logger.info("[cv-assembly] loaded %d verified facts for user=%s", len(facts), user_id)
    return facts


# ═════════════════════════════════════════════════════════════════════════════
# Top-level assembly
# ═════════════════════════════════════════════════════════════════════════════

def assemble_cv(
    facts:            list[VerifiedFact],
    gap_entities:     list[str],
    matched_entities: list[str],
    candidate_title:  str,
    llm_client=None,
    max_bullets:      int = 12,
    company_vibe:     Optional[str] = None,
) -> AssembledCv:
    """
    Build the tailored CV content.

    Every bullet passes the zero-hallucination gate:
      LLM path:            phrase_bullet_llm → validate_bullet → accept/reject
      Rejected or no LLM:  render_bullet_deterministic (always valid by
                           construction — it only recombines fact fields).

    company_vibe (from CompanyProfile.financial_vibe) biases fact SELECTION
    toward efficiency or scaling evidence — it never touches fact content.

    `unserved_gaps` lists JD must-haves with no supporting facts. They are
    intentionally ABSENT from the output CV — surfacing them to the user
    (via Ariel's STAR-story flow) is the only legitimate way to close them.
    """
    selected, unserved = select_facts_for_gaps(
        facts, gap_entities, matched_entities, max_bullets, company_vibe=company_vibe,
    )

    bullets: list[BulletDraft] = []
    rejected = 0
    for fact in selected:
        text: Optional[str] = None
        if llm_client is not None:
            draft = phrase_bullet_llm(fact, llm_client)
            if draft and validate_bullet(draft, [fact]):
                text = draft
            elif draft:
                rejected += 1
        if text is None:
            text = render_bullet_deterministic(fact)
        bullets.append(BulletDraft(text=text, fact_ids=[fact.fact_id], entity=fact.entity, validated=True))

    # Skills section: only entities that have at least one backing fact.
    evidenced = sorted({f.entity for f in facts})

    summary = (
        f"{candidate_title} with evidence-backed strengths in "
        f"{', '.join(evidenced[:5])}."
        if evidenced else candidate_title
    )

    return AssembledCv(
        summary=summary,
        bullets=bullets,
        skills=evidenced,
        unserved_gaps=unserved,
        rejected_count=rejected,
    )
