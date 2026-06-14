"""OutreachEngine — generates data-backed LinkedIn InMail messages.

Loads verified_profile from user_master_profile.json, selects the top-2
confidence skills and the cultural signals that best match the target
company, then writes a <100-word message with a verified-metrics hook
and an optional B2C bridge via the TAMA/Microsoft AR project.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

_MASTER_PROFILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "user_master_profile.json")
)

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "at", "to", "for",
    "is", "was", "as", "by", "on", "with",
}

# ── Company value database ────────────────────────────────────────────────────

_COMPANY_DB: dict[str, list[str]] = {
    "monday.com":   ["Data-Driven", "Ownership", "Fast-Paced", "Transparency"],
    "wix":          ["Creative", "Fast-Paced", "Customer Obsession", "Collaborative"],
    "google":       ["Data-Driven", "Structured", "Collaborative", "High Performance"],
    "meta":         ["Fast-Paced", "Ownership", "High Performance", "Data-Driven"],
    "fiverr":       ["Fast-Paced", "Entrepreneurial", "Startup Energy", "Collaborative"],
    "appsflyer":    ["Data-Driven", "High Performance", "Structured", "Collaborative"],
    "similar web":  ["Data-Driven", "Structured", "High Performance", "Collaborative"],
    "lemonade":     ["Fast-Paced", "Ownership", "Innovative", "Customer Obsession"],
    "default":      ["Collaborative", "High Performance", "Ownership"],
}

# ── B2C detection ─────────────────────────────────────────────────────────────

_B2C_PATTERN = re.compile(
    r"\b(consumer|b2c|marketplace|app|mobile|retail|ecommerce|e.commerce|"
    r"gaming|media|entertainment|travel|food|fashion|lifestyle|social|"
    r"ticketing|events|streaming|content|platform)\b",
    re.IGNORECASE,
)

_B2C_SENTENCE = (
    "I also led UX review for the TAMA AR Web App "
    "(Microsoft × Reichman University × Tel Aviv Museum of Art), "
    "shipping a consumer-facing digital product from wireframes to launch."
)

# ── Cultural signal → human label ────────────────────────────────────────────

_SIGNAL_LABELS: dict[str, str] = {
    "Data-Driven":        "data-driven decision making",
    "Fast-Paced":         "speed and execution",
    "High Performance":   "high performance",
    "Startup Energy":     "startup energy",
    "Collaborative":      "cross-functional collaboration",
    "Customer Obsession": "customer obsession",
    "Ownership":          "deep ownership",
    "Process-Driven":     "operational rigour",
    "Structured":         "structured execution",
    "Creative":           "creative thinking",
    "Client-Focused":     "client-first culture",
    "Stable":             "stability and trust",
    "High Pressure":      "performance under pressure",
    "Innovative":         "continuous innovation",
    "Entrepreneurial":    "entrepreneurial thinking",
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    words = re.findall(r"\b[a-z]{2,}\b", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _trim_to_limit(text: str, limit: int = 99) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    result: list[str] = []
    total = 0
    for sent in sentences:
        wc = _word_count(sent)
        if total + wc > limit:
            break
        result.append(sent)
        total += wc
    return " ".join(result)


def _best_company_values(company_name: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9.\s]", "", company_name.lower()).strip()
    best_key, best_sim = "default", 0.0
    for key in _COMPANY_DB:
        if key == "default":
            continue
        sim = _similarity(normalized, key)
        if sim > best_sim:
            best_sim, best_key = sim, key
    return _COMPANY_DB[best_key]


def _pick_signal(profile_signals: list[str], company_values: list[str]) -> str:
    """Return the single profile signal that best matches company values."""
    scored = sorted(
        profile_signals,
        key=lambda s: max(_similarity(s, v) for v in company_values),
        reverse=True,
    )
    if scored:
        return _SIGNAL_LABELS.get(scored[0], scored[0].lower())
    return "high-impact execution"


# ── Engine ────────────────────────────────────────────────────────────────────

class OutreachEngine:

    def __init__(self, profile_path: str = _MASTER_PROFILE_PATH) -> None:
        self.profile_path = os.path.abspath(profile_path)
        raw = self._load()
        self._vp: dict[str, Any] = raw.get("verified_profile", {})

    def _load(self) -> dict[str, Any]:
        if not os.path.exists(self.profile_path):
            raise FileNotFoundError(f"Profile not found: {self.profile_path}")
        with open(self.profile_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _top_skills(self, n: int = 2) -> list[dict]:
        skills = self._vp.get("skill_verification", [])
        return sorted(skills, key=lambda s: s["confidence_score"], reverse=True)[:n]

    def _cultural_signals(self) -> list[str]:
        return self._vp.get("synthesized_identity", {}).get("cultural_fit_signals", [])

    @staticmethod
    def _is_b2c(company_name: str, context: str = "") -> bool:
        return bool(_B2C_PATTERN.search(company_name + " " + context))

    def generate_linkedin_message(
        self,
        target_company: str,
        company_context: str = "",
        recipient_name: str = "",
    ) -> str:
        if not self._vp:
            raise RuntimeError(
                "verified_profile missing — run ProfileVerifier.run() first."
            )

        top_skills = self._top_skills(2)
        skill_1 = top_skills[0] if top_skills else {"skill": "Product Strategy", "confidence_score": 1.0}
        skill_2 = top_skills[1] if len(top_skills) > 1 else {"skill": "Stakeholder Management", "confidence_score": 1.0}
        conf_pct = int(round(skill_1["confidence_score"] * 100))

        company_values = _best_company_values(target_company)
        profile_signals = self._cultural_signals()
        culture_phrase = _pick_signal(profile_signals, company_values)

        greeting = f"Hi {recipient_name}," if recipient_name else "Hi,"

        hook = (
            f"{greeting} I see {target_company} values {culture_phrase} — "
            f"that's exactly how I operate."
        )

        proof = (
            f"My background in {skill_1['skill']} is verified at {conf_pct}% confidence "
            f"through cross-referencing my 25+ shipped features, "
            f"and my {skill_2['skill']} track record spans 1,000+ organiser accounts "
            f"on a live-event B2B2C SaaS platform."
        )

        b2c_line = _B2C_SENTENCE if self._is_b2c(target_company, company_context) else ""

        cta = f"Would love 15 minutes to explore how this maps to {target_company}'s roadmap."

        candidates = [
            " ".join(filter(None, [hook, proof, b2c_line, cta])),
            " ".join(filter(None, [hook, proof, cta])),
            " ".join(filter(None, [hook, proof])),
        ]

        for msg in candidates:
            if _word_count(msg) <= 99:
                return msg

        return _trim_to_limit(candidates[-1], limit=99)

    def render(
        self,
        target_company: str,
        company_context: str = "",
        recipient_name: str = "",
    ) -> dict[str, Any]:
        message = self.generate_linkedin_message(
            target_company, company_context, recipient_name
        )
        top_skills = self._top_skills(2)
        company_values = _best_company_values(target_company)
        culture_phrase = _pick_signal(self._cultural_signals(), company_values)
        return {
            "target_company": target_company,
            "recipient": recipient_name or "(not specified)",
            "is_b2c": self._is_b2c(target_company, company_context),
            "matched_culture_signal": culture_phrase,
            "top_skills_used": [
                {
                    "skill": s["skill"],
                    "confidence_score": s["confidence_score"],
                    "confidence_pct": f"{int(round(s['confidence_score'] * 100))}%",
                }
                for s in top_skills
            ],
            "word_count": _word_count(message),
            "message": message,
        }


    def generate_message(self, target_company: str, company_context: str = "") -> dict[str, Any]:
        """Backward-compatible wrapper used by app.py and the Live Opportunities tab."""
        result = self.render(target_company, company_context)
        top_skills = self._top_skills(2)
        company_values = _best_company_values(target_company)
        signal = _pick_signal(self._cultural_signals(), company_values)
        why = (
            f"Opening with '{signal}' mirrors {target_company}'s culture, "
            f"and anchoring on a {int(round(top_skills[0]['confidence_score'] * 100))}%-confidence "
            f"'{top_skills[0]['skill']}' score converts a soft claim into verifiable evidence — "
            f"reducing recruiter skepticism before the first reply."
            if top_skills else ""
        )
        return {
            **result,
            "matched_cultural_signals": [signal] if signal else [],
            "why_this_works": why,
        }


if __name__ == "__main__":
    import pprint

    engine = OutreachEngine()

    cases = [
        ("Monday.com",  "",                                   "Lior"),
        ("Wix",         "consumer website builder platform",  "Dana"),
        ("Fiverr",      "B2C freelance marketplace",          ""),
        ("AppsFlyer",   "mobile measurement B2B SaaS",        "Yael"),
        ("Lemonade",    "consumer insurance app",             "Tal"),
    ]

    for company, ctx, name in cases:
        result = engine.render(company, ctx, name)
        sep = "─" * 64
        print(f"\n{sep}")
        print(f"  {result['target_company']}  |  B2C={result['is_b2c']}  |  {result['word_count']} words")
        print(f"  Signal: {result['matched_culture_signal']}")
        print(sep)
        print(result["message"])
