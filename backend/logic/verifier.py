"""ProfileVerifier — cross-source verification and conflict-resolution module.

Compares job history from the Master Profile (PDF-derived) against simulated
external data (LinkedIn, Gmail) and writes a verified_profile back to
user_master_profile.json.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from typing import Any

_MASTER_PROFILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "user_master_profile.json")
)

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "at", "to", "for",
    "is", "was", "as", "by", "on", "with", "cs",
}

# ── Evidence levels ────────────────────────────────────────────────────────────

LEVEL_CLAIM      = 1   # Mentioned in CV / Master Profile only
LEVEL_VALIDATION = 2   # Cross-referenced on at least one external platform
LEVEL_MASTERY    = 3   # Supported by a user-supplied project context (≥40 chars)

_LEVEL_LABELS: dict[int, str] = {
    LEVEL_CLAIM:      "Level 1 — Claim",
    LEVEL_VALIDATION: "Level 2 — Validation",
    LEVEL_MASTERY:    "Level 3 — Demonstrated Mastery",
}

_CONTEXT_PROMPTS: dict[str, str] = {
    "Product Strategy": (
        "Describe a specific roadmap trade-off you managed: what did you deprioritise, "
        "why, and what was the measurable outcome?"
    ),
    "Stakeholder Management": (
        "Describe a situation where two stakeholders had conflicting priorities. "
        "How did you reach alignment without formal authority?"
    ),
    "Team Leadership": (
        "Describe a moment when a team member was underperforming. "
        "What action did you take and what changed as a result?"
    ),
    "Customer Success": (
        "Describe a customer who was at risk of churning. "
        "What specific steps did you take and what was the retention outcome?"
    ),
    "SQL/Python": (
        "Describe a data problem you solved with SQL or Python. "
        "What was the query or script, and what decision did it inform?"
    ),
    "SaaS Ops": (
        "Describe an operational breakdown on your platform. "
        "How did you identify it, respond in real time, and prevent recurrence?"
    ),
    "PRD/Jira": (
        "Walk through a Jira ticket you wrote from discovery to acceptance criteria. "
        "What made it sprint-ready and unambiguous for the engineer?"
    ),
    "Agile/Scrum": (
        "Describe how you changed a sprint mid-cycle. "
        "What triggered the change and how did you manage stakeholder expectations?"
    ),
}

_DEFAULT_CONTEXT_PROMPT: str = (
    "Describe a specific project where you applied this skill: "
    "what was the challenge, what action did you take, and what was the measurable result?"
)

# ── Simulated external data ────────────────────────────────────────────────────

_LINKEDIN_DATA: dict[str, Any] = {
    "job_history": [
        {
            "title": "Team Lead – Partnerships & Support",
            "company": "GO-OUT",
            "start": "2025-01",
            "end": "2026-04",
        },
        {
            "title": "Partnership Manager",
            "company": "Go-Out",
            "start": "2023-03",
            "end": "2025-01",
        },
        {
            "title": "Customer Support Specialist",
            "company": "Go Out",
            "start": "2023-01",
            "end": "2023-04",
        },
        {
            "title": "Operations & Pension Referent",
            "company": "Clal Insurance Agency",
            "start": "2021-06",
            "end": "2023-05",
        },
        {
            "title": "Reception & Administration",
            "company": "Reuveni Pridan Advertising",
            "start": "2020-10",
            "end": "2022-06",
        },
    ],
    "endorsements": {
        "Product Strategy": 12,
        "Team Leadership": 18,
        "Customer Success": 22,
        "Jira": 9,
        "SQL": 3,
        "SaaS Operations": 7,
        "Stakeholder Management": 14,
        "Agile Scrum": 6,
        "Python": 1,
    },
}

_GMAIL_CERTIFICATIONS: list[dict] = [
    {"name": "Product Management", "issuer": "Pitango Academy / Triola", "date": "2024-06"},
    {"name": "Advanced Data Science & Relational Databases", "issuer": "Online", "date": "2025-01"},
    {"name": "Agile Scrum Foundation", "issuer": "CertiProf", "date": "2023-11"},
]

_MASTER_JOB_HISTORY: list[dict] = [
    {
        "title": "Team Lead – Partnerships & Support",
        "company": "GO-OUT",
        "start": "2025-01",
        "end": "2026-04",
    },
    {
        "title": "Partnership Manager (CS)",
        "company": "GO-OUT",
        "start": "2023-03",
        "end": "2025-01",
    },
    {
        "title": "Customer Support",
        "company": "GO-OUT",
        "start": "2023-01",
        "end": "2023-03",
    },
    {
        "title": "Operations & Pension Referent",
        "company": "Insurance Agency",
        "start": "2021-01",
        "end": "2023-05",
    },
    {
        "title": "Reception & Admin",
        "company": "Reuveni Pridan",
        "start": "2020-09",
        "end": "2022-06",
    },
]

_SKILLS: list[str] = [
    "Product Strategy",
    "Team Leadership",
    "Customer Success",
    "SQL/Python",
    "SaaS Ops",
    "PRD/Jira",
    "Stakeholder Management",
    "Agile/Scrum",
]

# ── Integrity guidance ────────────────────────────────────────────────────────

_FLAG_GUIDANCE: dict[str, str] = {
    "DATE_DISCREPANCY_START": (
        "Verify the start date against your original offer letter or contract. "
        "If LinkedIn is accurate, update your Master Profile to match. "
        "Do not stretch dates to hide gaps — background checks cross-reference payroll records."
    ),
    "DATE_DISCREPANCY_END": (
        "Verify the end date against your final payslip or termination letter. "
        "If LinkedIn is accurate, update your Master Profile to match. "
        "Do not stretch dates to hide gaps — background checks cross-reference payroll records."
    ),
    "TITLE_MISMATCH": (
        "Check your original employment contract for your official job title. "
        "Use the exact title from your contract — not a self-promoted version. "
        "If you held an informal title, note it in parentheses: 'Official Title (functioned as X)'."
    ),
    "COMPANY_NAME_MISMATCH": (
        "Use the company's legal registered name as it appears on your payslip or contract. "
        "Harmonise informal variants (e.g. 'Go-Out' vs 'GO-OUT Ltd') across all platforms."
    ),
    "NO_MATCH": (
        "This role has no matching entry on LinkedIn. "
        "Add it to your LinkedIn profile so background checkers can verify it. "
        "Missing entries raise red flags even when the role was fully legitimate."
    ),
}

_LOW_SKILL_GUIDANCE: str = (
    "No sufficient external proof found for this skill. "
    "To raise confidence: (1) forward a relevant certification email to your Gmail account, "
    "(2) ask a colleague or manager for a LinkedIn endorsement, or "
    "(3) add a public project or GitHub link that demonstrates this skill. "
    "Do not claim a skill at a level you cannot demonstrate in an interview."
)

_GLASSDOOR_DB: dict[str, dict] = {
    "go out": {
        "core_values": ["Customer Obsession", "High Performance", "Move Fast", "Ownership"],
        "employee_sentiment": ["Fast-Paced", "High Pressure", "Collaborative", "Startup Energy"],
    },
    "clal insurance": {
        "core_values": ["Integrity", "Long-Term Thinking", "Client Trust", "Stability"],
        "employee_sentiment": ["Structured", "Process-Driven", "Stable", "Conservative"],
    },
    "insurance agency": {
        "core_values": ["Integrity", "Client Trust", "Stability"],
        "employee_sentiment": ["Structured", "Process-Driven", "Stable"],
    },
    "reuveni pridan": {
        "core_values": ["Creativity", "Excellence", "Brand Integrity"],
        "employee_sentiment": ["Creative", "Fast-Paced", "Client-Focused"],
    },
    "default": {
        "core_values": ["Performance", "Integrity", "Innovation"],
        "employee_sentiment": ["Professional", "Collaborative"],
    },
}


class ProfileVerifier:

    def __init__(self, profile_path: str = _MASTER_PROFILE_PATH) -> None:
        self.profile_path = os.path.abspath(profile_path)
        self._profile: dict[str, Any] = self._load_profile()

    # ── I/O ───────────────────────────────────────────────────────────────────

    def _load_profile(self) -> dict[str, Any]:
        if not os.path.exists(self.profile_path):
            return {}
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_profile(self) -> None:
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.profile_path), suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(self._profile, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.profile_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # ── Fuzzy matching (re-only) ──────────────────────────────────────────────

    @staticmethod
    def _tokens(text: str) -> set[str]:
        words = re.findall(r"\b[a-z]{2,}\b", text.lower())
        return {w for w in words if w not in _STOPWORDS}

    def _similarity(self, a: str, b: str) -> float:
        ta, tb = self._tokens(a), self._tokens(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    # ── Date utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_ym(date_str: str) -> tuple[int, int] | None:
        m = re.fullmatch(r"(\d{4})-(\d{2})", date_str.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.fullmatch(r"(\d{4})", date_str.strip())
        if m:
            return int(m.group(1)), 1
        return None

    def _months_diff(self, d1: str, d2: str) -> int | None:
        p1, p2 = self._parse_ym(d1), self._parse_ym(d2)
        if p1 is None or p2 is None:
            return None
        return abs((p1[0] * 12 + p1[1]) - (p2[0] * 12 + p2[1]))

    # ── Job history verification ──────────────────────────────────────────────

    def verify_job_history(
        self,
        master_jobs: list[dict] | None = None,
        linkedin_jobs: list[dict] | None = None,
    ) -> list[dict]:
        master_jobs = master_jobs or _MASTER_JOB_HISTORY
        linkedin_jobs = linkedin_jobs or _LINKEDIN_DATA["job_history"]

        results: list[dict] = []
        used: set[int] = set()

        for mj in master_jobs:
            best_score, best_idx = 0.0, -1
            for i, lj in enumerate(linkedin_jobs):
                if i in used:
                    continue
                score = (
                    0.6 * self._similarity(mj["company"], lj["company"])
                    + 0.4 * self._similarity(mj["title"], lj["title"])
                )
                if score > best_score:
                    best_score, best_idx = score, i

            entry: dict[str, Any] = {
                "master": mj,
                "linkedin": linkedin_jobs[best_idx] if best_idx >= 0 else None,
                "match_score": round(best_score, 3),
                "flags": [],
            }

            if best_idx < 0 or best_score < 0.25:
                entry["flags"].append({
                    "type": "NO_MATCH",
                    "detail": (
                        f"No LinkedIn entry matches '{mj['title']}' at '{mj['company']}'"
                    ),
                    "guidance": _FLAG_GUIDANCE["NO_MATCH"],
                })
                results.append(entry)
                continue

            used.add(best_idx)
            lj = linkedin_jobs[best_idx]

            company_sim = self._similarity(mj["company"], lj["company"])
            if company_sim < 0.5:
                entry["flags"].append({
                    "type": "COMPANY_NAME_MISMATCH",
                    "detail": (
                        f"'{mj['company']}' vs '{lj['company']}' "
                        f"(similarity={company_sim:.2f})"
                    ),
                    "guidance": _FLAG_GUIDANCE["COMPANY_NAME_MISMATCH"],
                })

            title_sim = self._similarity(mj["title"], lj["title"])
            if title_sim < 0.4:
                entry["flags"].append({
                    "type": "TITLE_MISMATCH",
                    "detail": (
                        f"'{mj['title']}' vs '{lj['title']}' "
                        f"(similarity={title_sim:.2f})"
                    ),
                    "guidance": _FLAG_GUIDANCE["TITLE_MISMATCH"],
                })

            for field in ("start", "end"):
                mv, lv = mj.get(field), lj.get(field)
                if mv and lv:
                    diff = self._months_diff(mv, lv)
                    if diff is not None and diff > 2:
                        flag_key = f"DATE_DISCREPANCY_{field.upper()}"
                        entry["flags"].append({
                            "type": flag_key,
                            "detail": (
                                f"{field}: master='{mv}' linkedin='{lv}' "
                                f"({diff} months apart)"
                            ),
                            "guidance": _FLAG_GUIDANCE[flag_key],
                        })

            results.append(entry)

        return results

    # ── Skill validation ──────────────────────────────────────────────────────

    def validate_skills(
        self,
        skills: list[str] | None = None,
        linkedin_endorsements: dict[str, int] | None = None,
        gmail_certs: list[dict] | None = None,
    ) -> list[dict]:
        skills = skills or _SKILLS
        linkedin_endorsements = linkedin_endorsements or _LINKEDIN_DATA["endorsements"]
        gmail_certs = gmail_certs or _GMAIL_CERTIFICATIONS
        skill_contexts: dict[str, str] = self._profile.get("skill_contexts", {})

        validated: list[dict] = []
        for skill in skills:
            sources: list[str] = []
            score = 0.0

            # Level 1 baseline — Master Profile (PDF)
            sources.append("Master Profile (PDF)")
            score += 0.25

            # LinkedIn endorsements — fuzzy match → Level 2 candidate
            best_endorsement: tuple[str, int] | None = None
            best_end_sim = 0.0
            for endorsed, count in linkedin_endorsements.items():
                sim = self._similarity(skill, endorsed)
                if sim > best_end_sim:
                    best_end_sim, best_endorsement = sim, (endorsed, count)

            linkedin_hit = False
            if best_endorsement and best_end_sim >= 0.35:
                endorsed_name, count = best_endorsement
                sources.append(f"LinkedIn: '{endorsed_name}' ({count} endorsements)")
                score += min(0.4, 0.04 * count)
                linkedin_hit = True

            # Gmail certifications — token overlap → Level 2 candidate
            cert_hit = False
            for cert in gmail_certs:
                cert_sim = self._similarity(skill, cert["name"])
                if cert_sim >= 0.25:
                    sources.append(f"Gmail cert: '{cert['name']}' ({cert['issuer']})")
                    score += 0.35
                    cert_hit = True
                    break

            # Determine base evidence level from external cross-references
            level = LEVEL_VALIDATION if (linkedin_hit or cert_hit) else LEVEL_CLAIM

            # Level 3 — user-supplied project context stored in profile JSON
            user_context = skill_contexts.get(skill, "").strip()
            if user_context and len(user_context) >= 40:
                sources.append("User-provided project context")
                score = min(1.0, score + 0.35)
                level = LEVEL_MASTERY

            final_score = round(min(score, 1.0), 3)
            skill_entry: dict = {
                "skill": skill,
                "confidence_score": final_score,
                "evidence_level": level,
                "evidence_label": _LEVEL_LABELS[level],
                "verified_by": sources,
                "user_context": user_context or None,
            }

            if level < LEVEL_MASTERY:
                prompt = _CONTEXT_PROMPTS.get(skill, _DEFAULT_CONTEXT_PROMPT)
                skill_entry["context_prompt"] = (
                    f"To reach Level 3 for '{skill}': {prompt}"
                )
            if final_score < 0.7 and level < LEVEL_MASTERY:
                skill_entry["guidance"] = _LOW_SKILL_GUIDANCE

            validated.append(skill_entry)

        return sorted(validated, key=lambda x: x["confidence_score"], reverse=True)

    # ── Glassdoor simulation ──────────────────────────────────────────────────

    def fetch_company_culture(self, company_name: str) -> dict:
        normalized = re.sub(r"[^a-z\s]", "", re.sub(r"[-_/]", " ", company_name.lower())).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        best_key, best_sim = "default", 0.0
        for key in _GLASSDOOR_DB:
            if key == "default":
                continue
            sim = self._similarity(normalized, key)
            if sim > best_sim:
                best_sim, best_key = sim, key

        data = _GLASSDOOR_DB[best_key]
        return {
            "company": company_name,
            "source": "Glassdoor (simulated)",
            "matched_db_key": best_key if best_key != "default" else None,
            "match_confidence": round(best_sim, 3),
            "core_values": data["core_values"],
            "employee_sentiment": data["employee_sentiment"],
        }

    # ── Orchestration ─────────────────────────────────────────────────────────

    def build_verified_profile(self) -> dict[str, Any]:
        job_verifications = self.verify_job_history()
        skill_validations = self.validate_skills()

        discrepancies = [
            {
                "job": v["master"]["title"],
                "company": v["master"]["company"],
                "flags": v["flags"],
            }
            for v in job_verifications
            if v["flags"]
        ]

        companies = list({j["company"] for j in _MASTER_JOB_HISTORY})
        company_cultures = {c: self.fetch_company_culture(c) for c in companies}

        avg_skill_conf = (
            sum(s["confidence_score"] for s in skill_validations) / len(skill_validations)
            if skill_validations
            else 0.0
        )
        flag_penalty = len(discrepancies) * 0.05
        overall_confidence = round(max(0.0, min(1.0, avg_skill_conf - flag_penalty)), 3)

        return {
            "candidate": "Ron Morim",
            "verification_timestamp": datetime.utcnow().isoformat(),
            "overall_confidence": overall_confidence,
            "job_history_verification": job_verifications,
            "skill_verification": skill_validations,
            "company_cultures": company_cultures,
            "discrepancies": discrepancies,
            "synthesized_identity": {
                "name": "Ron Morim",
                "verified_title": "Product Manager / Team Lead",
                "verified_skills": [
                    s["skill"]
                    for s in skill_validations
                    if s["confidence_score"] >= 0.5
                ],
                "high_confidence_skills": [
                    s for s in skill_validations if s["confidence_score"] >= 0.7
                ],
                "narrative_tags": [
                    "rapid_promotion",
                    "operational_complexity",
                    "emotional_intelligence",
                    "resilience",
                ],
                "cultural_fit_signals": sorted({
                    sentiment
                    for cult in company_cultures.values()
                    for sentiment in cult.get("employee_sentiment", [])
                }),
            },
        }

    def run(self) -> dict[str, Any]:
        verified_profile = self.build_verified_profile()
        self._profile["verified_profile"] = verified_profile
        self._profile["last_updated"] = datetime.utcnow().isoformat()
        self._save_profile()
        return verified_profile


    def save_skill_contexts(self, contexts: dict[str, str]) -> None:
        """Persist user-provided skill narratives; Level 3 unlocked when ≥40 chars saved."""
        existing = self._profile.get("skill_contexts", {})
        existing.update({k: v.strip() for k, v in contexts.items() if v.strip()})
        self._profile["skill_contexts"] = existing
        self._save_profile()
        self._profile = self._load_profile()

    def match_against_jd(
        self,
        jd_text: str,
        candidate_skills: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Score candidate against a JD, weighting Level 3 mastery most heavily.

        Level 1 weight 0.25 · Level 2 weight 0.60 · Level 3 weight 1.00.
        Recruiters who filter by verified depth will see Level 3 skills ranked first.
        """
        candidate_skills = candidate_skills or self.validate_skills()
        jd_tokens = self._tokens(jd_text)

        _weight = {LEVEL_CLAIM: 0.25, LEVEL_VALIDATION: 0.60, LEVEL_MASTERY: 1.00}

        jd_matches: list[dict] = []
        for sk in candidate_skills:
            skill_tokens = self._tokens(sk["skill"])
            relevance = len(skill_tokens & jd_tokens) / max(len(skill_tokens), 1)
            if relevance > 0:
                level = sk.get("evidence_level", LEVEL_CLAIM)
                jd_matches.append({
                    "skill":          sk["skill"],
                    "relevance_to_jd": round(relevance, 3),
                    "evidence_level":  level,
                    "evidence_label":  sk.get("evidence_label", _LEVEL_LABELS[level]),
                    "jd_match_score":  round(relevance * _weight[level], 3),
                    "user_context":    sk.get("user_context"),
                })

        jd_matches.sort(key=lambda x: x["jd_match_score"], reverse=True)

        # JD keywords not covered by any candidate skill token
        candidate_union: set[str] = set()
        for sk in candidate_skills:
            candidate_union |= self._tokens(sk["skill"])
        gaps = [t for t in jd_tokens if t not in candidate_union and len(t) > 4]

        level3_count = sum(1 for s in jd_matches if s["evidence_level"] == LEVEL_MASTERY)
        overall = sum(s["jd_match_score"] for s in jd_matches) / max(len(jd_matches), 1)

        return {
            "jd_word_count":           len(re.findall(r"\S+", jd_text)),
            "matched_skills":          jd_matches,
            "coverage_gaps":           gaps[:10],
            "level3_requirements_met": level3_count,
            "total_matched":           len(jd_matches),
            "overall_jd_score":        round(overall, 3),
            "recruiter_summary": (
                f"{level3_count} of {len(jd_matches)} matched skills have "
                f"Level 3 — Demonstrated Mastery for this role."
            ),
        }


if __name__ == "__main__":
    import pprint
    result = ProfileVerifier().run()
    pprint.pprint(result, depth=3)
    print(f"\noverall_confidence: {result['overall_confidence']}")
    print(f"discrepancies found: {len(result['discrepancies'])}")
