"""
MasterProfileService — B2C structured user profile store.

Persists the Master Profile to data/master_profile.json at the project root.
All writes are atomic (tempfile -> os.replace) so a crash mid-save never
corrupts the existing file.

This module is intentionally separate from:
  backend/engines/master_profile.py   — bullet-improvement placeholder system
  backend/supplemental_answers.json   — flat Q&A list for LLM context injection
  backend/personal_overrides.json     — phone/location overrides for USER_PROFILE

merge_answers() writes to BOTH this structured store AND supplemental_store.py
to keep the two persistence layers in sync.  The flat supplemental store feeds
build_full_text() so the TailorAgent always sees answered questions as
established profile facts.

Public API
----------
load()                                -> dict
save(profile)                         -> None          (atomic)
get_cached_answer(question_id)        -> str | None
merge_answers(answers)                -> int           (count of new entries)
bootstrap_from_supplemental()         -> int           (count imported)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
# backend/services/master_profile_service.py
#   .parents[0] = backend/services/
#   .parents[1] = backend/
#   .parents[2] = project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR     = _PROJECT_ROOT / "data"
_PROFILE_PATH = _DATA_DIR / "master_profile.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _empty_profile() -> dict:
    """Return a fresh profile scaffold seeded from USER_PROFILE where possible."""
    try:
        from backend.services.user_profile import USER_PROFILE
        p = USER_PROFILE.get("personal", {})
        personal = {
            "full_name":    p.get("name",     ""),
            "email":        p.get("email",    ""),
            "phone":        p.get("phone",    ""),
            "linkedin_url": p.get("linkedin", ""),
            "location":     p.get("location", ""),
        }
    except Exception:
        personal = {
            "full_name": "", "email": "", "phone": "",
            "linkedin_url": "", "location": "",
        }

    return {
        "version":          1,
        "last_updated":     _now_iso(),
        "personal":         personal,
        "metrics":          {},
        "role_preferences": {
            "target_titles":       [],
            "preferred_locations": [],
            "work_type":           "any",
            "salary_min_usd":      None,
        },
        # Populated by ResearcherAgent — keyed by entity name (lowercase)
        "enriched_entities": {},
    }


# ── Core persistence ──────────────────────────────────────────────────────────

def load() -> dict:
    """
    Load the profile from disk.  Returns a fresh scaffold (and creates the
    file) if the profile is missing or corrupt.

    Also syncs any stored phone/location back into USER_PROFILE so the PDF
    builder always has the latest contact info even after a process restart.
    """
    if _PROFILE_PATH.exists():
        try:
            profile = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(profile, dict) and profile.get("version"):
                _sync_personal_to_user_profile(profile)
                return profile
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[master_profile] Could not load %s (%s) — starting fresh",
                _PROFILE_PATH, exc,
            )

    # File missing or corrupt — create a clean one
    profile = _empty_profile()
    try:
        save(profile)
        logger.info("[master_profile] Created new profile at %s", _PROFILE_PATH)
    except Exception as exc:
        logger.warning("[master_profile] Could not write new profile: %s", exc)

    return profile


def save(profile: dict) -> None:
    """
    Atomically write profile to disk via tempfile + os.replace.
    Updates last_updated timestamp before writing.
    """
    profile["last_updated"] = _now_iso()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=_DATA_DIR, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, _PROFILE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Answer cache ──────────────────────────────────────────────────────────────

def get_cached_answer(question_id: str) -> str | None:
    """
    Return the stored answer for question_id, or None if not present.

    MVP: answers are returned regardless of confidence level.
    P2: low-confidence answers (updated_at > 180 days) should be surfaced
        to the user for verification before re-use.
    """
    if not question_id:
        return None
    try:
        profile = load()
        entry = profile.get("metrics", {}).get(question_id)
        if entry and isinstance(entry, dict):
            value = str(entry.get("value", "")).strip()
            if value:
                return value
    except Exception as exc:
        logger.warning("[master_profile] get_cached_answer failed for '%s': %s", question_id, exc)
    return None


def merge_answers(answers: dict[str, str]) -> int:
    """
    Write new question_id -> answer pairs into profile["metrics"].

    Behaviour:
    - Always updates "updated_at" for any key that is already present.
    - Sets source="supplemental", confidence="high" for all merged entries.
    - Writes to master_profile.json (structured) AND supplemental_store
      (flat, for LLM context injection) to keep both stores in sync.
    - Returns the count of *newly written* entries (existing keys that are
      merely updated are not counted).

    Never raises — write failures are logged and silently swallowed so a
    profile persistence error never blocks CV generation.
    """
    if not answers:
        return 0

    newly_written = 0
    try:
        profile = load()
        metrics = profile.setdefault("metrics", {})

        for qid, raw_answer in answers.items():
            answer = str(raw_answer or "").strip()
            if not answer:
                continue
            now = _now_iso()
            if qid in metrics:
                # Update timestamp only — preserve the original created_at
                metrics[qid]["value"]      = answer
                metrics[qid]["updated_at"] = now
                metrics[qid]["confidence"] = "high"
            else:
                metrics[qid] = {
                    "value":      answer,
                    "source":     "supplemental",
                    "confidence": "high",
                    "created_at": now,
                    "updated_at": now,
                }
                newly_written += 1

        save(profile)

        logger.info(
            "[master_profile] merge_answers: %d new / %d updated (total metrics: %d)",
            newly_written,
            len(answers) - newly_written,
            len(metrics),
        )
    except Exception as exc:
        logger.error("[master_profile] merge_answers failed: %s", exc)
        # Fall through to supplemental_store write regardless

    # ── Keep supplemental_store in sync ───────────────────────────────────────
    # supplemental_store feeds build_full_text() → TailorAgent context.
    # It de-duplicates on its own (skips already-present IDs).
    try:
        from backend.services.supplemental_store import save as save_supplemental
        save_supplemental(answers)
    except Exception as exc:
        logger.warning("[master_profile] supplemental_store sync failed: %s", exc)

    return newly_written


# ── Skill proficiency extraction ─────────────────────────────────────────────

_ACADEMIC_SIGNALS: frozenset[str] = frozenset({
    "academic", "study", "studies", "studied", "course", "coursework",
    "university", "school", "college", "classroom", "thesis",
    "only in", "not professionally", "no professional",
})
_NONE_SIGNALS: frozenset[str] = frozenset({
    "no experience", "never used", "not familiar", "no knowledge",
    "haven't used", "have not used", "no background", "no formal",
    "don't have", "do not have",
})
_PROFESSIONAL_SIGNALS: frozenset[str] = frozenset({
    "professional", "work experience", "industry", "company",
    "client", "production", "shipped", "deployed", "years of", "at work",
})
_SKILL_KEY_STOP_WORDS: frozenset[str] = frozenset({
    "usage", "context", "experience", "level", "proficiency",
    "background", "knowledge", "skill", "details", "info", "history",
})


def get_skill_proficiencies() -> dict[str, str]:
    """
    Return {skill_name: proficiency_level} extracted from verify_* entries
    in master_profile["metrics"].

    proficiency_level values:
      "academic"     — used in studies/education but not professionally
      "professional" — confirmed professional experience
      "none"         — no experience at all
      "unknown"      — fact stored but level cannot be determined

    Skill name is derived from the metric key:
      "verify_python_usage_context"     → "python"
      "verify_machine_learning_context" → "machine learning"
    """
    try:
        profile = load()
        metrics = profile.get("metrics", {})
        result: dict[str, str] = {}

        for key, entry in metrics.items():
            if not key.startswith("verify_"):
                continue

            # Build skill name from the key words before any stop word
            remainder = key[len("verify_"):]          # e.g. "python_usage_context"
            words     = remainder.split("_")
            skill_words: list[str] = []
            for w in words:
                if w in _SKILL_KEY_STOP_WORDS:
                    break
                skill_words.append(w)
            skill = " ".join(skill_words).strip()
            if not skill or len(skill) < 2:
                continue

            value = str(entry.get("value", "")).lower()

            if any(sig in value for sig in _NONE_SIGNALS):
                level = "none"
            elif any(sig in value for sig in _ACADEMIC_SIGNALS):
                level = "academic"
            elif any(sig in value for sig in _PROFESSIONAL_SIGNALS):
                level = "professional"
            else:
                level = "unknown"

            result[skill] = level
            logger.debug("[master_profile] proficiency: %s → %s", skill, level)

        return result

    except Exception as exc:
        logger.warning("[master_profile] get_skill_proficiencies failed: %s", exc)
        return {}


# ── Profile update from verify/chat interaction ───────────────────────────────

async def update_profile_from_interaction(
    history: list[dict],
    verdict: str,
    summary: str,
) -> int:
    """
    Parse a verify/chat Q&A transcript and persist factual corrections the
    candidate stated (e.g. "I only used Python in studies, not professionally")
    into master_profile["metrics"] via merge_answers().

    Uses claude-haiku for fast, cheap extraction. Returns the number of new
    profile entries written. Never raises.
    """
    if not history or verdict not in ("verified", "failed"):
        return 0

    try:
        import os
        import anthropic as _anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("[master_profile] update_profile_from_interaction: ANTHROPIC_API_KEY not set")
            return 0

        lines: list[str] = []
        for entry in history:
            role    = entry.get("role", "")
            content = entry.get("content", "")
            if role == "agent":
                lines.append(f"Agent: {content}")
            elif role == "user":
                lines.append(f"Candidate: {content}")
        transcript = "\n".join(lines)

        prompt = (
            "You are analyzing a job-fit interview transcript to extract factual statements "
            "the candidate made about their own experience.\n\n"
            f"TRANSCRIPT:\n{transcript}\n\n"
            f"VERDICT: {verdict}\nSUMMARY: {summary}\n\n"
            "Extract ONLY concrete, factual statements the candidate made about themselves — "
            "specific skills, tools, years of experience, projects, or context limitations "
            "(e.g. 'only used X in studies', 'led a team of N', 'certified in Y').\n\n"
            "Return a JSON object where each key is a short snake_case identifier "
            "(e.g. 'python_usage_context', 'team_leadership_size') and each value is "
            "the candidate's exact factual statement.\n\n"
            "Return ONLY the JSON object. If no concrete facts were stated, return {}."
        )

        client = _anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model       = "claude-haiku-4-5-20251001",
            max_tokens  = 400,
            temperature = 0.0,
            messages    = [{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw_lines = raw.splitlines()
            raw = "\n".join(raw_lines[1:-1] if raw_lines[-1].strip() == "```" else raw_lines[1:])
        raw = raw.strip()

        facts = json.loads(raw)
        if not isinstance(facts, dict) or not facts:
            return 0

        prefixed = {f"verify_{k}": str(v) for k, v in facts.items() if k and v}
        count = merge_answers(prefixed)
        logger.info("[master_profile] update_profile_from_interaction: %d fact(s) stored", count)
        return count

    except Exception as exc:
        logger.warning("[master_profile] update_profile_from_interaction failed: %s", exc)
        return 0


# ── Bootstrap migration ───────────────────────────────────────────────────────

def bootstrap_from_supplemental() -> int:
    """
    One-time migration: import all entries from the flat supplemental_answers.json
    into master_profile.json["metrics"], skipping keys already present.

    Idempotent — safe to call on every application startup.
    Returns the count of entries imported.
    """
    try:
        from backend.services.supplemental_store import load_all
        entries = load_all()
    except Exception as exc:
        logger.warning("[master_profile] bootstrap: could not read supplemental store: %s", exc)
        return 0

    if not entries:
        return 0

    try:
        profile = load()
        metrics = profile.setdefault("metrics", {})
        imported = 0
        now = _now_iso()

        for entry in entries:
            qid    = str(entry.get("id",     "") or "").strip()
            answer = str(entry.get("answer", "") or "").strip()
            if not qid or not answer:
                continue
            if qid in metrics:
                continue  # already present — skip
            metrics[qid] = {
                "value":      answer,
                "source":     "supplemental",
                "confidence": "high",
                "created_at": now,
                "updated_at": now,
            }
            imported += 1

        if imported:
            save(profile)
            logger.info(
                "[master_profile] bootstrap: imported %d answer(s) from supplemental store",
                imported,
            )
        return imported

    except Exception as exc:
        logger.warning("[master_profile] bootstrap failed: %s", exc)
        return 0


# ── Enriched entities (Researcher Agent output) ───────────────────────────────

def save_enriched_entities(entities: list[dict]) -> None:
    """
    Persist the list of EnrichedEntity dicts (from ResearcherAgent) into
    profile["enriched_entities"], keyed by lowercased entity name.
    Merges with any existing entries — does not replace the whole section.
    Never raises.
    """
    if not entities:
        return
    try:
        profile = load()
        bucket: dict = profile.setdefault("enriched_entities", {})
        for entity in entities:
            name = str(entity.get("name", "")).strip()
            if name:
                bucket[name.lower()] = entity
        save(profile)
        logger.info(
            "[master_profile] save_enriched_entities: stored %d entity/entities",
            len(entities),
        )
    except Exception as exc:
        logger.error("[master_profile] save_enriched_entities failed: %s", exc)


def get_enriched_entities() -> list[dict]:
    """Return all enriched entities as a list, sorted by name. Never raises."""
    try:
        profile = load()
        return sorted(
            profile.get("enriched_entities", {}).values(),
            key=lambda e: str(e.get("name", "")),
        )
    except Exception as exc:
        logger.warning("[master_profile] get_enriched_entities failed: %s", exc)
        return []


def get_enriched_entity(name: str) -> dict | None:
    """Return the enriched entity for a given name (case-insensitive), or None."""
    try:
        profile = load()
        return profile.get("enriched_entities", {}).get(name.lower())
    except Exception:
        return None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _sync_personal_to_user_profile(profile: dict) -> None:
    """
    Sync phone and location from the profile back into the in-memory
    USER_PROFILE so the PDF builder always has the latest contact fields,
    even if personal_overrides.json and the master profile diverged.
    """
    personal = profile.get("personal", {})
    for field in ("phone", "location"):
        value = str(personal.get(field, "") or "").strip()
        if value:
            try:
                from backend.services.user_profile import save_personal_field
                save_personal_field(field, value)
            except Exception:
                pass  # never let a sync failure break profile loading
