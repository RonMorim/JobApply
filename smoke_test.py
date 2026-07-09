import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(override=True)

from backend.agents.matching_engine import MatchingEngineAgent
from models.job import JobAnalysis, RawJobPosting
from models.user import UserProfile

async def run_test():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("CRITICAL: ANTHROPIC_API_KEY MISSING")
        return

    engine = MatchingEngineAgent()
    
    # עדכון פרופיל עם הוכחות כרונולוגיות כדי "לשבור" את שגיאת ה-0 שנים
    my_profile = UserProfile(
        full_name="Jamie Smith",
        current_role="Product Manager",
        skills=[
            "Product Manager at Go-Out (2022-2025): Led B2C product roadmap and Agile sprints",
            "Data Analysis: 3 years of using Python for funnel optimization and conversion metrics",
            "Collaboration: Managed cross-functional R&D and UX teams for mobile app delivery",
            "Strategy: Defined product requirements and KPIs for consumer-facing features"
        ],
        experience_years=3, # אנחנו משאירים 3, אבל מוסיפים הוכחה בטקסט למעלה
        location="Israel"
    )

    junior_posting = RawJobPosting(
        id="jr-123",
        title="Associate Product Manager",
        company="Monday.com",
        source_url="https://monday.com/jobs",
        raw_text="Entry level PM role. Focus on execution and specs. Looking for 1-3 years of experience.",
        scraped_at=datetime.utcnow().isoformat()
    )

    senior_posting = RawJobPosting(
        id="sr-456",
        title="Senior Product Manager",
        company="Monday.com",
        source_url="https://monday.com/jobs",
        raw_text="Senior leadership role. 7+ years of experience mandatory. Strategic vision and team leadership.",
        scraped_at=datetime.utcnow().isoformat()
    )

    for label, posting in [("JUNIOR", junior_posting), ("SENIOR", senior_posting)]:
        print(f"\n--- TESTING {label} ROLE ---")
        
        analysis = JobAnalysis(
            job_id=posting.id,
            required_skills=["Product Management", "Execution", "Agile"],
            nice_to_have_skills=["Python"],
            seniority_level="junior" if label == "JUNIOR" else "senior",
            is_remote=False,
            company="Monday.com",
            location="Tel Aviv",
            summary=f"A {label} PM role at Monday."
        )

        try:
            match = await engine.score(posting, analysis, my_profile)
            print(f"[{label}] MATCH_SCORE: {match.score}")
            print(f"[{label}] CULTURE_FIT: {match.culture_fit_score}")
            print(f"[{label}] CRITICAL_GAPS: {len(match.detailed_analysis.critical_gaps)}")
            
            if match.reasons:
                print(f"[{label}] REASONS: {[r.label for r in match.reasons]}")
                
        except Exception as e:
            print(f"ERROR IN {label}: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(run_test())