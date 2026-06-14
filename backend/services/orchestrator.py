from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional, TypedDict

import httpx
from bs4 import BeautifulSoup
from langgraph.graph import END, StateGraph
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

import backend.services.agent_store as store
import backend.services.job_store as job_store
from backend.services.user_profile import (
    USER_PROFILE,
    TRAIT_CLUSTERS,
    get_candidate_name,
    get_all_companies,
    get_all_roles_text,
    get_narrative,
)

logger = logging.getLogger(__name__)

# ── Dynamic Candidate Extraction ──────────────────────────────────────────────

def _get_candidate_seniority() -> int:
    """Calculates professional span dynamically from USER_PROFILE dates."""
    exp = USER_PROFILE.get("experience", [])
    if not exp: return 3
    years = []
    for e in exp:
        found = re.findall(r"20\d{2}", str(e.get("period", "")))
        if found: years.extend([int(y) for y in found])
    return 2026 - min(years) if years else 3

def _get_held_titles() -> frozenset[str]:
    """Extracts all titles held by the candidate."""
    titles = set()
    for e in USER_PROFILE.get("experience", []):
        if e.get("role"): titles.add(e["role"].lower())
        for sub in e.get("roles", []):
            if sub.get("title"): titles.add(sub["title"].lower())
    return frozenset(titles)

# ── Workflow State ─────────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    url:          str
    job_info:     dict
    gap_analysis: dict
    why_ron:      str
    truth_report: dict
    passed:       bool
    error:        Optional[str]

# ── Node 1: Scraper (Full Playwright Implementation) ───────────────────────────

async def _fetch_with_playwright(url: str) -> tuple[str, dict]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            # Try specific containers
            for sel in [".job-description", "#job-details", "main"]:
                try:
                    await page.wait_for_selector(sel, timeout=3000)
                    body = await page.locator(sel).first.inner_text()
                    return await page.content(), {"body_text": body}
                except: continue
            return await page.content(), {"body_text": await page.locator("body").inner_text()}
        finally: await browser.close()

async def scraper_node(state: AnalysisState) -> dict:
    url = state["url"]
    store.set_active("s1", f"Scraping job data from {url}")
    try:
        html, meta = await _fetch_with_playwright(url)
        soup = BeautifulSoup(html, "lxml")
        title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "Unknown Role"
        
        return {
            "job_info": {
                "title": title,
                "description": meta.get("body_text", "")[:4000],
                "requirements": [] # Extracted dynamically in next node
            }
        }
    except Exception as e:
        return {"error": str(e)}

# ── Node 2: Sourcing Specialist (Universal Intelligence) ──────────────────────

async def sourcing_specialist_node(state: AnalysisState) -> dict:
    job = state["job_info"]
    name = get_candidate_name()
    store.set_active("s2", f"Matching requirements for {name}")
    
    desc = job.get("description", "").lower()
    titles_held = _get_held_titles()
    years_exp = _get_candidate_seniority()

    # Universal Seniority Logic
    req_years_match = re.search(r"(\d+)\+?\s*years?", desc)
    min_req_years = int(req_years_match.group(1)) if req_years_match else 2
    
    seniority_pts = 25 if years_exp >= min_req_years else 15
    if any(kw in job['title'].lower() for kw in ["senior", "lead", "head"]):
        seniority_pts = 28 if years_exp >= 5 else 18

    # Match Logic (Simplified for B2B)
    hard_misses = []
    if min_req_years > years_exp + 2:
        hard_misses.append({"requirement": f"{min_req_years}+ years exp", "penalty": 15, "severity": "high"})

    # Final Score Calculation
    final_score = min(99, 60 + seniority_pts - (len(hard_misses) * 15))
    if hard_misses: final_score = min(final_score, 88)

    return {
        "gap_analysis": {
            "overall_fit_score": final_score,
            "candidate": name,
            "hard_misses": hard_misses
        }
    }

# ── Node 3: Content Strategist (The Narrative) ───────────────────────────────

async def content_strategist_node(state: AnalysisState) -> dict:
    name = get_candidate_name()
    score = state["gap_analysis"]["overall_fit_score"]
    
    report = f"""# Recruiter Report: {name}
Match Score: {score}/100

## Why this candidate?
The candidate demonstrates strong alignment based on {len(get_all_companies())} verified roles.
Key highlight: {_get_candidate_seniority()} years of cumulative professional impact.
"""
    return {"why_ron": report}

# ── Node 4: Quality Guard ─────────────────────────────────────────────────────

async def quality_guard_node(state: AnalysisState) -> dict:
    score = state["gap_analysis"]["overall_fit_score"]
    # B2B Skeptic: Penalize high scores if no leadership titles exist
    if score > 90 and not any(kw in str(_get_held_titles()) for kw in ["lead", "manager", "head"]):
        score = 84
    
    return {"passed": True, "truth_report": {"final_score": score}}

# ── Build Graph ───────────────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    g = StateGraph(AnalysisState)
    g.add_node("scraper", scraper_node)
    g.add_node("sourcing_specialist", sourcing_specialist_node)
    g.add_node("content_strategist", content_strategist_node)
    g.add_node("quality_guard", quality_guard_node)
    g.set_entry_point("scraper")
    g.add_edge("scraper", "sourcing_specialist")
    g.add_edge("sourcing_specialist", "content_strategist")
    g.add_edge("content_strategist", "quality_guard")
    g.add_edge("quality_guard", END)
    return g

_compiled = _build_graph().compile()

async def run_analysis(url: str) -> AnalysisState:
    initial = {"url": url, "job_info": {}, "gap_analysis": {}, "why_ron": "", "passed": False}
    result = await _compiled.ainvoke(initial)
    return result


if __name__ == "__main__":
    async def test():
        test_url = "https://www.comeet.com/jobs/example/123" # לינק לדוגמה
        print(f"--- Starting Test Analysis for: {test_url} ---")
        result = await run_analysis(test_url)
        print("\n--- Result Summary ---")
        print(f"Candidate: {result['gap_analysis']['candidate']}")
        print(f"Final Score: {result['gap_analysis']['overall_fit_score']}")
        print(f"Report Preview:\n{result['why_ron'][:500]}...")

    asyncio.run(test())