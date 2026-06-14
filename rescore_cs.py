"""
rescore_cs.py — single-use scoring variance verification script.

Fetches the 3 most recently added Customer Success jobs from the database,
bypasses the cache by re-scraping each URL, runs them through the updated
MatcherAgent (5-axis engine), and prints:
  · Job Title · Company · new match_score · scoring_rationale

Does NOT save results back to the database.

Run with the project venv:
    venv/bin/python rescore_cs.py
"""
import asyncio
import sqlite3
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Make project root importable ─────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.url_scraper import scrape_job_post          # noqa: E402
from backend.agents.matcher import MatcherAgent           # noqa: E402
from models.job import RawJobPosting                      # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH   = ROOT / "backend" / "jobs.db"
CATEGORY  = "Customer Success"
LIMIT     = 3
DIVIDER   = "─" * 72


def fetch_cs_jobs(limit: int = LIMIT) -> list[dict]:
    """Pull job_id, title, company, apply_url, score from DB for the category."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT job_id, title, company, apply_url, score
        FROM   jobs
        WHERE  category = ?
          AND  apply_url IS NOT NULL
        ORDER  BY posted_at DESC
        LIMIT  ?
        """,
        (CATEGORY, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


async def rescore_job(agent: MatcherAgent, job: dict) -> dict:
    """Re-scrape a URL and run the matcher. Returns enriched result dict."""
    url = job["apply_url"]

    print(f"\n  Scraping: {url}")
    try:
        scraped = await asyncio.to_thread(scrape_job_post, url)
    except Exception as exc:
        return {**job, "error": f"Scrape failed: {exc}", "new_score": None, "rationale": None}

    posting = RawJobPosting(
        id=str(uuid.uuid4()),
        title=scraped.title or job["title"],
        company=scraped.company or job["company"],
        source_url=url,
        raw_text=scraped.raw_text,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )

    print(f"  Analysing with MatcherAgent…")
    try:
        match = await agent.match(posting)
    except Exception as exc:
        return {**job, "error": f"Matcher failed: {exc}", "new_score": None, "rationale": None}

    return {
        **job,
        "error": None,
        "new_score": match.score,
        "rationale": match.scoring_rationale,
    }


def print_result(idx: int, result: dict) -> None:
    old_score = result.get("score", "?")
    new_score = result.get("new_score")

    print(f"\n{DIVIDER}")
    print(f"  [{idx}] {result['title']}")
    print(f"       {result['company']}")
    print(DIVIDER)

    if result.get("error"):
        print(f"  ERROR: {result['error']}")
        return

    delta = ""
    if isinstance(old_score, (int, float)) and isinstance(new_score, (int, float)):
        diff = new_score - old_score
        sign = "+" if diff >= 0 else ""
        delta = f"  (was {old_score:.1f}, Δ {sign}{diff:.1f})"

    print(f"  match_score : {new_score:.1f}{delta}")
    print()
    print("  scoring_rationale:")
    if result["rationale"]:
        for line in result["rationale"].splitlines():
            print("    " + line)
    else:
        print("    (none returned)")


async def main() -> None:
    print(f"\n{'═' * 72}")
    print(f"  rescore_cs.py — {CATEGORY} · top {LIMIT} jobs")
    print(f"  Database : {DB_PATH}")
    print(f"{'═' * 72}")

    jobs = fetch_cs_jobs(LIMIT)
    if not jobs:
        print(f"\n  No jobs found in category '{CATEGORY}'. Exiting.")
        return

    print(f"\n  Found {len(jobs)} job(s) to rescore:")
    for j in jobs:
        print(f"    · {j['title']} @ {j['company']}  (current score: {j['score']})")

    agent = MatcherAgent()
    results = []
    for job in jobs:
        result = await rescore_job(agent, job)
        results.append(result)

    print(f"\n\n{'═' * 72}")
    print("  RESULTS")
    print(f"{'═' * 72}")
    for i, result in enumerate(results, 1):
        print_result(i, result)

    # Summary variance check
    scores = [r["new_score"] for r in results if r["new_score"] is not None]
    if len(scores) >= 2:
        spread = max(scores) - min(scores)
        print(f"\n{DIVIDER}")
        print(f"  Variance check: min={min(scores):.1f}  max={max(scores):.1f}  spread={spread:.1f}")
        if spread < 5.0:
            print("  WARNING: spread < 5 points — scores may still be clustering.")
        else:
            print("  OK: spread indicates genuine score differentiation.")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    asyncio.run(main())
