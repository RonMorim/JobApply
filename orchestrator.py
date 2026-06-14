"""Candidate Command Center — single entry point for the full workflow.

Steps
-----
1. ProfileVerifier  — refresh verified_profile in user_master_profile.json.
2. LocalJobAnalyzer — score candidate fit against a target job spec.
3. OutreachEngine   — generate a tailored LinkedIn InMail.

No external API calls are made; all logic runs locally and deterministically.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from backend.logic.verifier import ProfileVerifier
from backend.logic.outreach_engine import OutreachEngine, _similarity

# ── Target job (Monday.com APM/PM) ────────────────────────────────────────────

_TARGET_COMPANY = "Monday.com"

_TARGET_JOB: dict[str, Any] = {
    "title": "Associate Product Manager",
    "company": _TARGET_COMPANY,
    "required_skills": [
        "Product Strategy",
        "Agile/Scrum",
        "Stakeholder Management",
        "Data Analysis",
        "User Research",
    ],
    "nice_to_have_skills": [
        "SQL",
        "Jira",
        "SaaS",
        "Customer Success",
        "B2B",
    ],
    "seniority": "mid",
    "domain": "B2B SaaS / Work OS",
    "years_required": 2,
}

# ── ASCII presentation helpers ────────────────────────────────────────────────

_WIDTH = 72


def _line(char: str = "─") -> str:
    return char * _WIDTH


def _box_top() -> str:
    return f"╔{'═' * (_WIDTH - 2)}╗"


def _box_bot() -> str:
    return f"╚{'═' * (_WIDTH - 2)}╝"


def _box_row(text: str = "") -> str:
    pad = _WIDTH - 4 - len(text)
    return f"║  {text}{' ' * max(pad, 0)}  ║"


def _section(title: str) -> None:
    print(f"\n  ┌─ {title} {'─' * max(0, _WIDTH - 6 - len(title))}┐")


def _section_end() -> None:
    print(f"  └{'─' * (_WIDTH - 4)}┘")


def _row(label: str, value: str, width: int = 24) -> None:
    print(f"  │  {label:<{width}} {value}")


def _banner(text: str) -> None:
    print(f"\n  {'▸'} {text}")


def _step_header(n: int, label: str) -> None:
    print(f"\n{_line('─')}")
    print(f"  STEP {n}  │  {label}")
    print(_line("─"))


def _ok(msg: str) -> None:
    print(f"  [OK]  {msg}")


def _warn(msg: str) -> None:
    print(f"  [!!]  {msg}")


# ── Local job fit analyzer ────────────────────────────────────────────────────

@dataclass
class FitResult:
    overall_score: int
    skills_score: float
    culture_score: float
    domain_score: float
    matched_required: list[str] = field(default_factory=list)
    matched_nice: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)


def _fuzzy_match_skill(candidate_skill: str, job_skills: list[str], threshold: float = 0.3) -> str | None:
    """Return the best-matching job skill above threshold, or None."""
    best_sim, best_match = 0.0, None
    for js in job_skills:
        sim = _similarity(candidate_skill, js)
        if sim > best_sim:
            best_sim, best_match = sim, js
    return best_match if best_sim >= threshold else None


def analyze_fit(verified_profile: dict[str, Any], job: dict[str, Any]) -> FitResult:
    skill_records: list[dict] = verified_profile.get("skill_verification", [])
    cultural_signals: list[str] = (
        verified_profile.get("synthesized_identity", {}).get("cultural_fit_signals", [])
    )
    company_cultures: dict[str, dict] = verified_profile.get("company_cultures", {})

    required = job["required_skills"]
    nice = job["nice_to_have_skills"]

    matched_required: list[str] = []
    matched_nice: list[str] = []
    skill_score_accum = 0.0

    for sr in skill_records:
        skill_name = sr["skill"]
        conf = sr["confidence_score"]

        req_hit = _fuzzy_match_skill(skill_name, required)
        if req_hit and req_hit not in matched_required:
            matched_required.append(req_hit)
            skill_score_accum += conf * 1.0

        nice_hit = _fuzzy_match_skill(skill_name, nice)
        if nice_hit and nice_hit not in matched_nice:
            matched_nice.append(nice_hit)
            skill_score_accum += conf * 0.4

    max_possible = len(required) * 1.0 + len(nice) * 0.4
    skills_score = min(1.0, skill_score_accum / max_possible) if max_possible else 0.0

    gaps = [r for r in required if r not in matched_required]

    # Culture fit: overlap between profile signals and known company domain keywords
    domain_tokens: set[str] = set()
    for phrase in [job["domain"], *[f["employee_sentiment"][0] for f in company_cultures.values() if f.get("employee_sentiment")]]:
        domain_tokens |= set(re.findall(r"[a-z]{3,}", phrase.lower()))

    culture_hits = sum(
        1 for sig in cultural_signals
        if any(_similarity(sig, kw) >= 0.4 for kw in ["fast-paced", "collaborative", "ownership", "data-driven", "structured"])
    )
    culture_score = min(1.0, culture_hits / max(len(cultural_signals), 1))

    # Domain match: SaaS / B2B keywords in the verified identity
    identity_text = " ".join([
        verified_profile.get("synthesized_identity", {}).get("verified_title", ""),
        *verified_profile.get("synthesized_identity", {}).get("narrative_tags", []),
    ]).lower()
    domain_hits = sum(1 for kw in ["saas", "b2b", "product"] if kw in identity_text)
    domain_score = min(1.0, domain_hits / 3)

    # Weighted composite: skills 50%, culture 30%, domain 20%
    composite = skills_score * 0.50 + culture_score * 0.30 + domain_score * 0.20
    overall_score = round(composite * 100)

    strengths = [f"Verified match on '{s}'" for s in matched_required]
    if matched_nice:
        strengths.append(f"Bonus coverage: {', '.join(matched_nice)}")

    return FitResult(
        overall_score=overall_score,
        skills_score=round(skills_score * 100, 1),
        culture_score=round(culture_score * 100, 1),
        domain_score=round(domain_score * 100, 1),
        matched_required=matched_required,
        matched_nice=matched_nice,
        gaps=gaps,
        strengths=strengths,
    )


# ── Score bar ─────────────────────────────────────────────────────────────────

def _score_bar(score: int, width: int = 30) -> str:
    filled = round(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:3d}/100"


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run(company: str = _TARGET_COMPANY, job: dict[str, Any] = _TARGET_JOB) -> None:
    t_start = time.monotonic()

    # ── Header ────────────────────────────────────────────────────────────────
    print(f"\n{_box_top()}")
    print(_box_row())
    print(_box_row("  CANDIDATE COMMAND CENTER"))
    print(_box_row(f"  Target: {job['title']} @ {company}"))
    print(_box_row())
    print(_box_bot())

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1 — ProfileVerifier
    # ══════════════════════════════════════════════════════════════════════════
    _step_header(1, "ProfileVerifier — syncing verified_profile")

    verifier = ProfileVerifier()
    verified = verifier.run()
    overall_conf = verified.get("overall_confidence", 0.0)
    discrepancies = verified.get("discrepancies", [])

    _ok(f"verified_profile written to user_master_profile.json")
    _ok(f"overall_confidence : {overall_conf:.3f}")

    if discrepancies:
        for d in discrepancies:
            for flag in d.get("flags", []):
                _warn(f"{flag['type']} — {flag['detail']}")
    else:
        _ok("No discrepancies detected across job history.")

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2 — Local job fit analysis
    # ══════════════════════════════════════════════════════════════════════════
    _step_header(2, f"Job Fit Analysis — {job['title']} @ {company}")

    fit = analyze_fit(verified, job)

    _section("Score Breakdown")
    _row("Overall fit", _score_bar(fit.overall_score))
    _row("Skills coverage", _score_bar(int(fit.skills_score)))
    _row("Culture alignment", _score_bar(int(fit.culture_score)))
    _row("Domain match", _score_bar(int(fit.domain_score)))
    _section_end()

    _section("Matched Required Skills")
    for s in fit.matched_required:
        print(f"  │    ✓ {s}")
    if fit.gaps:
        for g in fit.gaps:
            print(f"  │    ✗ {g}  (gap)")
    _section_end()

    if fit.matched_nice:
        _section("Nice-to-Have Coverage")
        for s in fit.matched_nice:
            print(f"  │    + {s}")
        _section_end()

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3 — OutreachEngine
    # ══════════════════════════════════════════════════════════════════════════
    _step_header(3, f"OutreachEngine — LinkedIn InMail for {company}")

    engine = OutreachEngine()
    result = engine.generate_message(company)

    _section("Message Metadata")
    _row("Cultural signals used", ", ".join(result["matched_cultural_signals"]))
    _row("Top skills used", ", ".join(s["skill"] for s in result["top_skills_used"]))
    _row("Word count", str(result["word_count"]))
    _section_end()

    _section("Generated InMail")
    for line in result["message"].splitlines():
        print(f"  │  {line}")
    _section_end()

    _section("Strategy Note")
    # Wrap "why_this_works" to fit within box width
    words = result["why_this_works"].split()
    line_buf: list[str] = []
    for word in words:
        if sum(len(w) + 1 for w in line_buf) + len(word) > _WIDTH - 10:
            print(f"  │  {'  '.join(line_buf)}")
            line_buf = [word]
        else:
            line_buf.append(word)
    if line_buf:
        print(f"  │  {' '.join(line_buf)}")
    _section_end()

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY VIEW
    # ══════════════════════════════════════════════════════════════════════════
    elapsed = time.monotonic() - t_start
    top3 = verified.get("skill_verification", [])[:3]

    print(f"\n{_line('═')}")
    print("  SUMMARY — CANDIDATE COMMAND CENTER")
    print(_line("═"))
    print(f"  Candidate      : {verified.get('candidate', 'Ron Morim')}")
    print(f"  Target role    : {job['title']} @ {company}")
    print(f"  Run time       : {elapsed:.2f}s")
    print(_line())
    print(f"  Final Score    : {_score_bar(fit.overall_score)}")
    print(f"  Data Confidence: {_score_bar(int(overall_conf * 100))}")
    print(_line())
    print("  Top 3 Verified Skills:")
    for i, sk in enumerate(top3, 1):
        bar = _score_bar(int(sk["confidence_score"] * 100), width=20)
        print(f"    {i}. {sk['skill']:<28} {bar}")
    print(_line())
    print("  LinkedIn InMail (first line):")
    first_line = result["message"].splitlines()[0]
    print(f"    \"{first_line}\"")
    print(_line("═"))
    print()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else _TARGET_COMPANY
    run(company=target)
