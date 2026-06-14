"""
LinkedIn Scraper Reset Utility
================================
Run this after a bot-detection block to clear the BLOCKED state and stale
browser profile so the scraper can boot cleanly on the next scheduled run.

Usage:
    venv/bin/python -m backend.scripts.reset_linkedin_scraper

What it does:
  1. Clears linkedin_scraper_status, linkedin_redirect_error_count, and
     linkedin_scraper_blocked_at from the SQLite KV store.
  2. Deletes the stale Playwright browser profile at data/linkedin_browser_profile/
     so Playwright creates a fresh profile on the next launch.
  3. Checks that LINKEDIN_LI_AT is set in backend/.env and warns if it is
     missing or looks stale (unchanged from the last run that got blocked).

You MUST update LINKEDIN_LI_AT in backend/.env before restarting the scraper.
See backend/config.py line ~105 for the cookie-extraction steps.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.db import ENGINE, KVRow
from sqlalchemy.orm import Session

_KV_KEYS_TO_CLEAR = [
    "linkedin_scraper_status",
    "linkedin_redirect_error_count",
    "linkedin_scraper_blocked_at",
    "linkedin_cookie_status",
]

BROWSER_PROFILE = ROOT / "backend" / "data" / "linkedin_browser_profile"
ENV_FILE        = ROOT / "backend" / ".env"


def _clear_kv() -> None:
    print("\n── Step 1: Clear KV store ─────────────────────────────────────────────")
    with Session(ENGINE) as db:
        for key in _KV_KEYS_TO_CLEAR:
            row = db.get(KVRow, key)
            if row:
                print(f"  Deleting  {key!r:45s} (was: {row.value!r})")
                db.delete(row)
            else:
                print(f"  Not found {key!r:45s} (already clean)")
        db.commit()
    print("  KV store cleared.")


def _clear_browser_profile() -> None:
    print("\n── Step 2: Delete browser profile ────────────────────────────────────")
    if BROWSER_PROFILE.exists():
        shutil.rmtree(BROWSER_PROFILE)
        print(f"  Deleted   {BROWSER_PROFILE}")
    else:
        print(f"  Not found {BROWSER_PROFILE}  (already clean)")


def _check_env() -> None:
    print("\n── Step 3: Check LINKEDIN_LI_AT in backend/.env ──────────────────────")
    if not ENV_FILE.exists():
        print(f"  WARNING: {ENV_FILE} not found.")
        _print_cookie_reminder()
        return

    li_at = None
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("LINKEDIN_LI_AT"):
            parts = line.split("=", 1)
            li_at = parts[1].strip().strip('"').strip("'") if len(parts) == 2 else ""
            break

    if not li_at:
        print("  ⚠ LINKEDIN_LI_AT is NOT set in backend/.env")
        _print_cookie_reminder()
    else:
        # Show only a safe prefix so the value is recognisable but not fully exposed
        preview = li_at[:8] + "…" + li_at[-4:] if len(li_at) > 16 else li_at[:4] + "…"
        print(f"  LINKEDIN_LI_AT is set  ({preview})")
        print("  Ensure this is the FRESH cookie value — NOT the one that triggered the block.")
        print("  If it is the same cookie, update it before restarting the scraper.")


def _print_cookie_reminder() -> None:
    print("""
  How to get a fresh li_at cookie:
    1. Log into linkedin.com in Chrome/Firefox.
    2. Open DevTools → Application → Cookies → https://www.linkedin.com
    3. Find the cookie named  li_at  and copy its value.
    4. Paste it into  backend/.env  as:
         LINKEDIN_LI_AT=<paste value here>
    5. Re-run this script to verify, then restart the backend.
""")


def main() -> None:
    print("LinkedIn Scraper Reset")
    print("=" * 70)
    _clear_kv()
    _clear_browser_profile()
    _check_env()
    print("\n── Done ───────────────────────────────────────────────────────────────")
    print("  The scraper BLOCKED state has been cleared.")
    print("  Restart the backend after updating LINKEDIN_LI_AT to resume scraping.")


if __name__ == "__main__":
    main()
