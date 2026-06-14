"""
backend.scrapers — pluggable job-source adapters.

Public surface:
    BaseScraper          abstract base class
    ComeetAdapter        Comeet ATS adapter
    LinkedInScraper      LinkedIn search adapter
    GotfriendsScraper    gotfriends.co.il adapter
    DialogScraper        dialog.co.il adapter
    NishaScraper         nisha.co.il adapter
    DrushimScraper       drushim.co.il adapter (RSS + BS4 + Hebrew JD parser)
    AllJobsScraper       alljobs.co.il adapter (JSON AJAX + BS4 fallback)
    ScraperManager       registry + runner
    SCRAPER_MANAGER      module-level singleton
    SCRAPER_CLASSES      adapter-name → class mapping
    scraper_from_config  build an adapter from a plain dict
    scrape_jd_text       route a single URL to the correct JD scraper
    get_scraper_for_url  return a BaseScraper instance for a source URL
"""
from backend.scrapers.base_scraper       import BaseScraper
from backend.scrapers.comeet_adapter     import ComeetAdapter
from backend.scrapers.linkedin_scraper   import LinkedInScraper
from backend.scrapers.gotfriends_scraper import GotfriendsScraper
from backend.scrapers.dialog_scraper     import DialogScraper
from backend.scrapers.nisha_scraper      import NishaScraper
from backend.scrapers.drushim_scraper    import DrushimScraper
from backend.scrapers.alljobs_scraper    import AllJobsScraper
from backend.scrapers.scraper_manager    import (
    ScraperManager,
    SCRAPER_MANAGER,
    SCRAPER_CLASSES,
    scraper_from_config,
)
from backend.scrapers.url_router         import scrape_jd_text, get_scraper_for_url

__all__ = [
    "BaseScraper",
    "ComeetAdapter",
    "LinkedInScraper",
    "GotfriendsScraper",
    "DialogScraper",
    "NishaScraper",
    "DrushimScraper",
    "AllJobsScraper",
    "ScraperManager",
    "SCRAPER_MANAGER",
    "SCRAPER_CLASSES",
    "scraper_from_config",
    "scrape_jd_text",
    "get_scraper_for_url",
]
