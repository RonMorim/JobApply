"""
AgentOrchestrator — wires the four agents into a sequential pipeline and
manages lifecycle (start, stop, health-check).

Pipeline:
  ScraperAgent → ProfileAnalyzerAgent → MatchingEngineAgent → AutoApplierAgent
"""
from __future__ import annotations

import asyncio
import logging

from backend.agents.scraper import ScraperAgent
from backend.agents.profile_analyzer import ProfileAnalyzerAgent
from backend.agents.matching_engine import MatchingEngineAgent
from backend.agents.auto_applier import AutoApplierAgent
from models.job import RawJobPosting
from models.user import UserProfile

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self) -> None:
        self.scraper   = ScraperAgent()
        self.analyzer  = ProfileAnalyzerAgent()
        self.matcher   = MatchingEngineAgent()
        self.applier   = AutoApplierAgent()

    async def start(self, user_profile: UserProfile) -> None:
        """Launch all agents concurrently."""
        logger.info("Starting agent pipeline")
        await asyncio.gather(
            self.scraper.run(),
            self._analyzer_loop(user_profile),
        )

    async def stop(self) -> None:
        await self.scraper.stop()

    async def _analyzer_loop(self, profile: UserProfile) -> None:
        """
        Consume postings emitted by the Scraper, analyze → match → (conditionally) apply.
        In production this would subscribe to a Redis stream; here it polls a queue.
        """
        # TODO: replace with Redis stream consumer
        while True:
            await asyncio.sleep(5)
