"""
Master Profile — persistent source of truth for CV placeholder answers.

Stores data in data/user_master_profile.json at the project root.
All reads and writes are atomic (write to a temp file, then rename) so a
crash mid-save never corrupts the existing profile.

Structure of user_master_profile.json
--------------------------------------
{
  "pm_transition_date": "2024-05",          // ISO year-month the user went functional-PM
  "global_hints": {                          // last value given per token — shown as hints
    "[X%]": "15%",
    "[N]": "7"
  },
  "finalized_improvements": {
    "<16-char sha256 of original_section>": {
      "original_section":   "...",
      "template":           "... [X%] ...",   // the improved_section with tokens intact
      "placeholder_values": {"[X%]": "23%"},
      "final_section":      "... 23% ...",
      "finalized_at":       "2026-04-23T12:00:00"
    }
  },
  "last_updated": "2026-04-23T12:00:00"
}
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Resolve path relative to project root regardless of where the script is run from
_PROJECT_ROOT = Path(__file__).resolve().parents[2]   # backend/engines/ → project root
_DATA_DIR     = _PROJECT_ROOT / "data"
_PROFILE_PATH = _DATA_DIR / "user_master_profile.json"


def _improvement_key(original_section: str) -> str:
    """Stable 16-char key derived from the original section text."""
    return hashlib.sha256(original_section.encode()).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class MasterProfile:
    """
    Read/write wrapper around data/user_master_profile.json.

    Usage
    -----
        mp = MasterProfile()
        mp.set_pm_transition_date("2024-05")
        mp.finalize_improvement(original, template, {"[X%]": "15%"}, final_text)
        mp.save()

        # Next session
        mp2 = MasterProfile()
        print(mp2.pm_transition_date)          # "2024-05"
        print(mp2.get_final_section(original)) # "...15%..."
    """

    def __init__(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if _PROFILE_PATH.exists():
            try:
                with _PROFILE_PATH.open(encoding="utf-8") as f:
                    data = json.load(f)
                logger.debug("Loaded master profile from %s", _PROFILE_PATH)
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load master profile (%s) — starting fresh", exc)
        return {
            "pm_transition_date":     None,
            "global_hints":           {},
            "finalized_improvements": {},
            "last_updated":           None,
        }

    def save(self) -> None:
        """Atomically write current state to disk."""
        self._data["last_updated"] = _now_iso()
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=_DATA_DIR, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _PROFILE_PATH)
            logger.debug("Master profile saved to %s", _PROFILE_PATH)
        except Exception:
            os.unlink(tmp_path)
            raise

    # ── PM transition date ────────────────────────────────────────────────────

    @property
    def pm_transition_date(self) -> str | None:
        return self._data.get("pm_transition_date")

    def set_pm_transition_date(self, value: str) -> None:
        self._data["pm_transition_date"] = value.strip()

    # ── Global hints (cross-section suggestions) ──────────────────────────────

    def get_hint(self, token: str) -> str | None:
        """Return the last value given for *token* across any section, or None."""
        return self._data["global_hints"].get(token)

    def _update_hint(self, token: str, value: str) -> None:
        self._data["global_hints"][token] = value

    # ── Per-improvement finalization ──────────────────────────────────────────

    def is_finalized(self, original_section: str) -> bool:
        key = _improvement_key(original_section)
        return key in self._data["finalized_improvements"]

    def get_final_section(self, original_section: str) -> str | None:
        """Return the already-finalized text for this section, or None."""
        key = _improvement_key(original_section)
        entry = self._data["finalized_improvements"].get(key)
        return entry["final_section"] if entry else None

    def get_placeholder_values(self, original_section: str) -> dict[str, str]:
        """Return the stored placeholder→value map for a finalized section."""
        key = _improvement_key(original_section)
        entry = self._data["finalized_improvements"].get(key, {})
        return entry.get("placeholder_values", {})

    def finalize_improvement(
        self,
        original_section: str,
        template: str,
        placeholder_values: dict[str, str],
        final_section: str,
    ) -> None:
        """
        Store the finalized improvement and update global hints.
        Overwrites any previous entry for the same original_section.
        """
        key = _improvement_key(original_section)
        self._data["finalized_improvements"][key] = {
            "original_section":   original_section,
            "template":           template,
            "placeholder_values": placeholder_values,
            "final_section":      final_section,
            "finalized_at":       _now_iso(),
        }
        # Propagate each answered token as a global hint for future sections
        for token, value in placeholder_values.items():
            self._update_hint(token, value)

    # ── Summary helpers ───────────────────────────────────────────────────────

    @property
    def finalized_count(self) -> int:
        return len(self._data["finalized_improvements"])

    def all_final_sections(self) -> list[str]:
        """Return every finalized CV bullet in finalization order."""
        return [
            entry["final_section"]
            for entry in self._data["finalized_improvements"].values()
        ]
