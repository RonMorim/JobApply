"""
CV Interview — Interactive Placeholder Resolution
=================================================
Runs the full analysis pipeline, then walks the user through every CV
improvement suggestion one by one, collecting real values for each
[Placeholder] token. Answers are saved permanently to
data/user_master_profile.json so sessions can be resumed.

Usage
-----
    cd /Users/ronmorim/Projects/JobApply_Venture
    python run_interview.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from agents.profile_analyzer import ProfileAnalyzerAgent
from engines.matching_engine import MatchingEngineAgent
from engines.optimization_engine import (
    OptimizationEngine,
    extract_placeholders,
    substitute_placeholders,
)
from engines.master_profile import MasterProfile
from models.job import RawJobPosting
from models.optimization import CVImprovement

# ── Display helpers ───────────────────────────────────────────────────────────

_W = 64   # terminal width for dividers

def _hr(char: str = "─") -> None:
    print(char * _W)

def _section(title: str) -> None:
    print()
    _hr("═")
    print(f"  {title}")
    _hr("═")

def _wrap(label: str, text: str, indent: int = 4) -> None:
    prefix = " " * indent
    wrapped = textwrap.fill(text, width=_W - indent,
                            initial_indent=prefix,
                            subsequent_indent=prefix)
    print(f"\n  {label}")
    print(wrapped)

def _ask(prompt: str, hint: str | None = None) -> str:
    """Blocking input with an optional hint shown in brackets."""
    hint_str = f"  [hint from previous session: {hint}]" if hint else ""
    if hint_str:
        print(hint_str)
    return input(f"  ➤ {prompt}: ").strip()


# ── Analysis phase (async) ────────────────────────────────────────────────────

async def _run_analysis(cv_path: str, chat_context: str, posting: RawJobPosting):
    """Run all three analysis steps and return (cv_text, user_profile, match, report)."""
    analyzer = ProfileAnalyzerAgent()
    engine   = MatchingEngineAgent()
    optimizer = OptimizationEngine()

    print(f"\n[1/3] Extracting CV text from {cv_path} …")
    cv_text = analyzer.extract_text_from_pdf(cv_path)
    if not cv_text:
        print("      ⚠  Could not extract text. Check the path and try again.")
        sys.exit(1)

    print("[2/3] Building candidate profile …")
    user_profile = await analyzer.analyze_profile(cv_text, chat_context)
    print(f"      ✓  {user_profile.years_of_experience} years experience detected, "
          f"seniority={user_profile.seniority_level}")

    print("[3/3] Scoring against job + generating CV suggestions …")
    job_analysis = await analyzer.analyze_posting(posting)
    match        = await engine.score(posting, job_analysis, user_profile)
    report       = await optimizer.generate_suggestions(
        user_profile=user_profile,
        match_analysis=match,
        cv_text=cv_text,
        target_role=f"{posting.title} at {posting.company}",
    )
    print(f"      ✓  Score {match.overall_score}/100 · "
          f"{len(report.improvements)} suggestion(s) generated")

    return cv_text, user_profile, match, report


# ── Interview phase (sync) ────────────────────────────────────────────────────

def _interview_improvement(
    item: CVImprovement,
    index: int,
    total: int,
    master: MasterProfile,
) -> str:
    """
    Walk the user through one CVImprovement. Returns the final section text.
    If the section was already finalized in a previous session, skip and return it.
    """
    _hr()
    print(f"\n  Suggestion {index}/{total}")
    _hr()

    # ── Already done in a prior session? ─────────────────────────────────────
    if master.is_finalized(item.original_section):
        cached = master.get_final_section(item.original_section)
        print("\n  ✅  Already answered in a previous session.")
        _wrap("FINAL BULLET:", cached)
        return cached

    # ── Show context ──────────────────────────────────────────────────────────
    _wrap("ORIGINAL:", item.original_section)
    _wrap("IMPROVED TEMPLATE:", item.improved_section)
    _wrap("WHY THIS CHANGE:", item.logic_behind_change)

    tokens = extract_placeholders(item.improved_section)

    if not tokens:
        # No placeholders — accept the improved section as-is
        print("\n  (No placeholders in this suggestion — accepting as written.)")
        master.finalize_improvement(
            item.original_section,
            item.improved_section,
            {},
            item.improved_section,
        )
        master.save()
        return item.improved_section

    # ── Collect values for each placeholder ──────────────────────────────────
    print(f"\n  Found {len(tokens)} placeholder(s) to fill in: "
          + ", ".join(tokens))
    print("  (Press Enter to skip a placeholder and leave it for later.)\n")

    values: dict[str, str] = {}
    for token in tokens:
        hint = master.get_hint(token)
        answer = _ask(f"Real value for {token}", hint=hint)
        if answer:
            values[token] = answer
        elif hint:
            use_hint = _ask(f"Use previous value '{hint}'? (y/n)", hint=None).lower()
            if use_hint == "y":
                values[token] = hint

    # ── Build final section ───────────────────────────────────────────────────
    final = substitute_placeholders(item.improved_section, values)

    # Mark any tokens the user left blank as "(TBD)"
    remaining = extract_placeholders(final)
    if remaining:
        print(f"\n  ℹ  {len(remaining)} placeholder(s) left blank: "
              + ", ".join(remaining))
        print("     They will appear as-is in the saved version.")

    _wrap("FINAL BULLET:", final)
    confirm = _ask("Save this version? (y/n/edit)", hint=None).lower()

    if confirm == "edit":
        print("  Type your fully custom version below (single line):")
        final = input("  ➤ ").strip() or final

    if confirm in ("y", "edit", ""):
        master.finalize_improvement(
            item.original_section,
            item.improved_section,
            values,
            final,
        )
        master.save()
        print("  ✅  Saved.")
    else:
        print("  ⏭  Skipped — not saved.")

    return final


def _ask_pm_transition(master: MasterProfile) -> None:
    """Ask for PM transition date once; skip if already stored."""
    if master.pm_transition_date:
        print(f"\n  📅  PM transition date already on record: {master.pm_transition_date}")
        change = _ask("Update it? (y/n)", hint=None).lower()
        if change != "y":
            return

    _section("PM Transition Date")
    print("  This is the date you started acting as a de-facto Product Owner / PM,")
    print("  even if your title was still Customer Success or Team Lead.")
    print("  Format: YYYY-MM  (e.g. 2024-05)\n")
    date_input = _ask("When did you transition into your PM-functional role?")
    if date_input:
        master.set_pm_transition_date(date_input)
        master.save()
        print(f"  ✅  Saved: {date_input}")


def _print_final_report(master: MasterProfile, score: int) -> None:
    """Print the complete set of finalized CV bullets."""
    _section("FINAL CV BULLETS — Ready to Use")
    finals = master.all_final_sections()
    if not finals:
        print("  (No bullets finalized yet.)")
        return

    pm_date = master.pm_transition_date
    if pm_date:
        print(f"  📅  PM transition date: {pm_date}")

    print(f"  📊  Original match score: {score}/100")
    print(f"  ✍   {len(finals)} bullet(s) rewritten\n")

    for i, bullet in enumerate(finals, start=1):
        _hr("·")
        print(f"  [{i}]  {bullet}")

    _hr("·")
    print("\n  Copy the bullets above into your CV.")
    print("  Replace any remaining [Placeholder] tokens with your real figures.")
    print(f"\n  Profile saved at: data/user_master_profile.json")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    _section("CV Interview — Placeholder Resolution")

    # ── Job & CV config ───────────────────────────────────────────────────────
    CV_PATH = "Ron_Morim_CV_PM.pdf"

    chat_context = """
    המשתמש רון מורים מעוניין לבצע מעבר רשמי לתפקידי Product Manager.
    למרות שהטייטל האחרון שלו ב-Go-Out היה Customer Success Team Lead, הוא תפקד כ-Product Owner בפועל החל ממאי 2024.
    הוא צבר ניסיון רב בכתיבת כרטיסי Jira, ניהול ספרינטים, ועבודה צמודה עם פיתוח על פיצ'רים של B2B2C.
    הוא סיים קורס ניהול מוצר ב-Pitango Academy ומחזיק בתואר במנהל עסקים וחדשנות דיגיטלית מרייכמן (מצטיין דיקן).
    הוא שולט ב-SQL (בסיסי), Figma ו-Jira.
    המערכת צריכה לתת משקל גבוה לניסיון המוצרי ה"חבוי" שלו בתוך תפקידי ה-CS.
    """

    posting = RawJobPosting(
        id="job-001",
        title="Associate Product Manager",
        company="Monday.com",
        source_url="https://monday.com",
        raw_text=(
            "Looking for a Product Manager with 1-3 years experience. "
            "B2C background and Python skills are a major plus."
        ),
        scraped_at=datetime.utcnow().isoformat(),
    )

    if not os.path.exists(CV_PATH):
        print(f"\n  ⚠  CV file not found: {CV_PATH}")
        print("     Update CV_PATH at the top of run_interview.py and try again.")
        sys.exit(1)

    # ── Run analysis (async) ──────────────────────────────────────────────────
    cv_text, user_profile, match, report = await _run_analysis(
        CV_PATH, chat_context, posting
    )

    # ── Load persistent profile ───────────────────────────────────────────────
    master = MasterProfile()
    already_done = master.finalized_count
    if already_done:
        print(f"\n  ℹ  Resuming session — {already_done} bullet(s) already answered.")

    # ── PM transition date (before improvements so it's on record) ────────────
    _ask_pm_transition(master)

    # ── Interview loop ────────────────────────────────────────────────────────
    _section(f"CV Improvements  ({len(report.improvements)} suggestion(s))")

    if not report.improvements:
        print("  (The engine produced no improvement suggestions this run.)")
    else:
        for idx, item in enumerate(report.improvements, start=1):
            _interview_improvement(item, idx, len(report.improvements), master)

    # ── Final output ──────────────────────────────────────────────────────────
    _print_final_report(master, match.overall_score)


if __name__ == "__main__":
    asyncio.run(main())
