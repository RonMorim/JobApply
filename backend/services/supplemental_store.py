"""
Persistent store for supplemental answers collected from the user during CV generation.

Answers are written to  backend/supplemental_answers.json  and survive process restarts.
build_full_text() in user_profile.py loads them so the TailorAgent treats answered
questions as established profile facts and never re-asks them.

Public API
----------
save(answers)     — persist new {id: answer} pairs (skips duplicates)
load_all()        — return list[dict] with all saved {id, answer} entries
get_as_text()     — return a formatted string block ready for LLM injection
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).resolve().parents[1] / "supplemental_answers.json"


def load_all() -> list[dict]:
    """Return all saved entries as a list of {id, answer} dicts."""
    if not _STORE_PATH.exists():
        return []
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("supplemental_store: could not read %s — %s", _STORE_PATH, exc)
        return []


def save(answers: dict[str, str]) -> int:
    """
    Append new question-id → answer pairs to the persistent store.
    Blank answers and IDs already present are silently skipped.

    Returns the number of newly saved entries.
    """
    if not answers:
        return 0

    existing     = load_all()
    existing_ids = {entry["id"] for entry in existing}

    added = 0
    for qid, answer in answers.items():
        clean = str(answer or "").strip()
        if not clean or qid in existing_ids:
            continue
        existing.append({"id": qid, "answer": clean})
        existing_ids.add(qid)
        added += 1

    if added:
        _STORE_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "supplemental_store: persisted %d new answer(s) to %s",
            added, _STORE_PATH,
        )

    return added


def get_as_text() -> str:
    """
    Return all saved answers as a formatted text block for injection into
    build_full_text().  Returns empty string when no answers are saved.
    """
    entries = load_all()
    if not entries:
        return ""
    lines = "\n".join(f"  [{e['id']}]: {e['answer']}" for e in entries)
    return (
        "PREVIOUSLY_ANSWERED_QUESTIONS "
        "(established profile facts — treat as authoritative, never re-ask):\n"
        + lines
    )
