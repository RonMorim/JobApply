import asyncio
import os
from backend.agents.profile_analyzer import ProfileAnalyzerAgent
from backend.engines.matching_engine import MatchingEngineAgent
from backend.engines.optimization_engine import OptimizationEngine
from models.job import RawJobPosting
from datetime import datetime

async def main():
    # אתחול הסוכנים
    analyzer = ProfileAnalyzerAgent()
    engine = MatchingEngineAgent()

    # --- הגדרות משתמש ---
    # 1.  כאן  הקובץ  שלך
    CV_PATH = "Ron_Morim_CV_PM.pdf"
    
    # 2. כאן נכנס "שיח הצ'אט" - הדברים שסיפרת לי ולא מופיעים ב-CV
    chat_context = """
    המשתמש רון מורים מעוניין לבצע מעבר רשמי לתפקידי Product Manager.
    למרות שהטייטל האחרון שלו ב-Go-Out היה Customer Success Team Lead, הוא תפקד כ-Product Owner בפועל החל ממאי 2024.
    הוא צבר ניסיון רב בכתיבת כרטיסי Jira, ניהול ספרינטים, ועבודה צמודה עם פיתוח על פיצ'רים של B2B2C.
    הוא סיים קורס ניהול מוצר ב-Pitango Academy ומחזיק בתואר במנהל עסקים וחדשנות דיגיטלית מרייכמן (מצטיין דיקן).
    הוא שולט ב-SQL (בסיסי), Figma ו-Jira.
    המערכת צריכה לתת משקל גבוה לניסיון המוצרי ה"חבוי" שלו בתוך תפקידי ה-CS.
    """

    print(f"--- שלב 1: מנתח את קורות החיים: {CV_PATH} ---")
    if not os.path.exists(CV_PATH):
        print(f"שגיאה: הקובץ {CV_PATH} לא נמצא בתיקייה!")
        return

    cv_text = analyzer.extract_text_from_pdf(CV_PATH)
    
    print("--- שלב 2: יוצר פרופיל מאוחד (CV + שיחות צ'אט) ---")
    user_profile = await analyzer.analyze_profile(cv_text, chat_context)
    
    print(f"פרופיל נוצר בהצלחה עבור המשתמש.")
    print(f"ניסיון שנמצא: {user_profile.years_of_experience} שנים")

    print("\n--- שלב 3: בדיקה מול משרה לדוגמה (Monday.com) ---")
    # כאן אנחנו מדמים משרה אמיתית
    job_text = "Looking for a Product Manager with 1-3 years experience. B2C background and Python skills are a major plus."
    
    mock_posting = RawJobPosting(
        id="job-001",
        title="Associate Product Manager",
        company="Monday.com",
        source_url="https://monday.com",
        raw_text=job_text,
        scraped_at=datetime.utcnow().isoformat()
    )
    
    # ניתוח המשרה והתאמה
    job_analysis = await analyzer.analyze_posting(mock_posting)
    match = await engine.score(mock_posting, job_analysis, user_profile)

    # ── Match Result ──────────────────────────────────────────────────────────
    overall   = getattr(match, "overall_score", "N/A")
    breakdown = getattr(match, "breakdown",     None)
    model     = getattr(match, "model_used",    "unknown")

    print("\n========================================")
    print(f"  תוצאת התאמה סופית : {overall}/100")
    print("----------------------------------------")
    if breakdown:
        print(f"  Skills Match      : {getattr(breakdown, 'skills_match',     'N/A'):.1f}/100")
        print(f"  Experience Match  : {getattr(breakdown, 'experience_match', 'N/A'):.1f}/100")
        print(f"  Domain Match      : {getattr(breakdown, 'domain_match',     'N/A'):.1f}/100")
        print(f"  Seniority Match   : {getattr(breakdown, 'seniority_match',  'N/A'):.1f}/100")
    print(f"  Model Used        : {model}")
    print("========================================")

    strengths = getattr(match, "strengths", [])
    if strengths:
        print("\n✅ Strengths:")
        for s in strengths:
            print(f"  + {s}")

    weaknesses = getattr(match, "weaknesses", [])
    if weaknesses:
        print("\n⚠️  Weaknesses:")
        for w in weaknesses:
            print(f"  - {w}")

    red_flags = getattr(match, "red_flags", [])
    if red_flags:
        print("\n🚩 Red Flags:")
        for flag in red_flags:
            print(f"  ! {flag}")

    recommendations = getattr(match, "recommendations", [])
    if recommendations:
        print("\n💡 Recommendations:")
        for r in recommendations:
            print(f"  → {r}")

    reasoning = getattr(match, "reasoning", "")
    if reasoning:
        print(f"\n📋 Reasoning:\n  {reasoning}")

    # ── Step 4: CV Optimization Suggestions ──────────────────────────────────
    print("\n\n--- שלב 4: CV Optimization Suggestions ---")
    try:
        optimizer = OptimizationEngine()
        report = await optimizer.generate_suggestions(
            user_profile=user_profile,
            match_analysis=match,
            cv_text=cv_text,
            target_role=f"{mock_posting.title} at {mock_posting.company}",
        )

        exec_summary = getattr(report, "executive_summary", "")
        if exec_summary:
            print(f"\n📌 Executive Summary:\n  {exec_summary}")

        priority = getattr(report, "priority_order", [])
        if priority:
            print(f"\n🎯 Priority Fix Order: {' → '.join(priority)}")

        improvements = getattr(report, "improvements", [])
        if not improvements:
            print("\n(No improvement suggestions were generated.)")
        else:
            print(f"\n({len(improvements)} suggestion(s) generated)\n")
            for i, item in enumerate(improvements, start=1):
                print(f"{'─' * 60}")
                print(f"  Suggestion #{i}")
                print(f"{'─' * 60}")

                original = getattr(item, "original_section", "")
                if original:
                    print(f"\n  📄 Original Section:\n    {original}")

                improved = getattr(item, "improved_section", "")
                if improved:
                    print(f"\n  ✏️  Improved Section:\n    {improved}")

                logic = getattr(item, "logic_behind_change", "")
                if logic:
                    print(f"\n  💡 Logic Behind Change:\n    {logic}")

                metrics = getattr(item, "added_metrics", [])
                if metrics:
                    print(f"\n  📊 Metrics / Placeholders to Fill In:")
                    for m in metrics:
                        print(f"    • {m}")

        model_used = getattr(report, "model_used", "unknown")
        print(f"\n  [Optimization model: {model_used}]")

    except Exception as exc:
        print(f"\n⚠️  CV Optimization step failed: {exc}")
        print("    (The match analysis above is still valid — this step is non-blocking.)")

if __name__ == "__main__":
    asyncio.run(main())