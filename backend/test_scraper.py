"""
Quick smoke-test for the ScraperAgent.

Instantiates the agent, runs one scrape cycle (not the infinite loop),
and verifies the health endpoint on the running FastAPI server.
"""
import asyncio
import httpx

from backend.agents.scraper import ScraperAgent, ScraperConfig


async def test_scraper_agent() -> None:
    print("=== ScraperAgent unit test ===")
    config = ScraperConfig(
        sources=["https://boards.greenhouse.io", "https://jobs.lever.co"],
        max_concurrent=2,
        request_timeout=10.0,
        delay_between_requests=0.1,
    )
    agent = ScraperAgent(config)

    postings: list = []
    async for p in agent._scrape_all():
        postings.append(p)

    print(f"Scrape cycle complete. Postings returned: {len(postings)}")
    print("PASS: ScraperAgent._scrape_all() ran without exception")


async def test_api_health() -> None:
    print("\n=== FastAPI health check ===")
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8000/health", timeout=5.0)
    assert resp.status_code == 200, f"Unexpected status: {resp.status_code}"
    print(f"GET /health -> {resp.status_code} {resp.json()}")
    print("PASS: FastAPI server is up")


async def test_agents_endpoint() -> None:
    print("\n=== Agents API endpoint ===")
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8000/api/agents/", timeout=5.0)
    assert resp.status_code == 200, f"Unexpected status: {resp.status_code}"
    agents = resp.json()
    print(f"GET /api/agents/ -> {len(agents)} agents returned")
    scraper = next((a for a in agents if a["name"] == "Scraper"), None)
    assert scraper is not None, "Scraper agent not found in response"
    print(f"Scraper agent: state={scraper['state']}, task={scraper['current_task']}")
    print("PASS: Agents endpoint OK")


async def main() -> None:
    await test_scraper_agent()
    await test_api_health()
    await test_agents_endpoint()
    print("\nAll tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
