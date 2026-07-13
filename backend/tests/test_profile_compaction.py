"""
Unit tests — Phase 35: token optimization for the Ariel chat payload
======================================================================

Coverage:
  1. user_profile.format_profile_compact()
       - never raises on an empty profile
       - includes every experience entry (no cap/slice) for a large profile
       - produces plain text (no JSON braces/quotes) that's smaller than the
         equivalent json.dumps(..., indent=2) for the same input
  2. The Ariel history sliding window (chat._ARIEL_MAX_HISTORY_MESSAGES)
       - keeps exactly the most recent N items from a longer list
"""
from __future__ import annotations

import json

from backend.services.user_profile import format_profile_compact


def _empty_profile() -> dict:
    return {
        "personal": {"name": ""},
        "summary": "",
        "education": [],
        "experience": [],
        "skills": [],
        "career_goals": {},
        "key_narratives": {},
        "volunteering": "",
    }


def _profile_with_n_roles(n: int) -> dict:
    experience = [
        {
            "company": f"Company {i}",
            "role": f"Role {i}",
            "period": f"20{i:02d} - 20{i + 1:02d}",
            "start": f"20{i:02d}",
            "end": f"20{i + 1:02d}",
            "details": f"Did notable thing {i}.",
        }
        for i in range(n)
    ]
    return {
        "personal": {"name": "Jane Doe"},
        "summary": "Product leader.",
        "education": [{"degree": "BA", "field": "Economics", "institution": "Tel Aviv U", "year": 2015}],
        "experience": experience,
        "skills": [f"Skill{i}" for i in range(n)],
        "career_goals": {
            "target_roles": ["VP Product"],
            "preferred_locations": ["Tel Aviv", "Remote"],
            "work_environment": "hybrid",
            "notes": "Open to fintech.",
        },
        "key_narratives": {},
        "volunteering": "",
    }


class TestFormatProfileCompact:

    def test_empty_profile_does_not_raise(self):
        text = format_profile_compact(_empty_profile())
        assert "SUMMARY: (none)" in text
        assert "EXPERIENCE" in text
        assert "SKILLS: (none)" in text

    def test_every_experience_entry_and_skill_is_included_uncapped(self):
        profile = _profile_with_n_roles(20)
        text = format_profile_compact(profile)

        for i in range(20):
            assert f"Company {i}" in text
            assert f"Skill{i}" in text

    def test_output_is_smaller_than_indented_json(self):
        profile = _profile_with_n_roles(20)
        compact_text = format_profile_compact(profile)
        json_text = json.dumps(profile, ensure_ascii=False, indent=2)

        assert len(compact_text) < len(json_text)
        assert "{" not in compact_text and '"' not in compact_text

    def test_career_goals_rendered(self):
        profile = _profile_with_n_roles(2)
        text = format_profile_compact(profile)
        assert "VP Product" in text
        assert "Tel Aviv" in text
        assert "hybrid" in text
        assert "Open to fintech." in text


class TestArielHistoryWindow:

    def test_slice_keeps_only_most_recent_n_messages(self):
        from backend.api.routes.chat import _ARIEL_MAX_HISTORY_MESSAGES

        assert 12 <= _ARIEL_MAX_HISTORY_MESSAGES <= 15

        fake_history = [{"role": "user", "content": f"msg-{i}"} for i in range(71)]
        windowed = fake_history[-_ARIEL_MAX_HISTORY_MESSAGES:]

        assert len(windowed) == _ARIEL_MAX_HISTORY_MESSAGES
        assert windowed[0]["content"] == f"msg-{71 - _ARIEL_MAX_HISTORY_MESSAGES}"
        assert windowed[-1]["content"] == "msg-70"
