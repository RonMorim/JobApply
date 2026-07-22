"""
LinkedIn "Israel jobs, last 3 hours" scraper - no login required.

Uses LinkedIn's public guest jobs API:
    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search

This endpoint returns the same job cards you'd see browsing LinkedIn
jobs while logged out. It supports:
    - keywords
    - location
    - f_TPR   (time posted range, in seconds -> r10800 = last 3 hours)
    - start   (pagination offset, 25 results per "page")

The script pulls results in BATCHES of `batch_size` pages (default 1 page
= 25 jobs per request), with a delay between each request and a longer
delay between batches, to stay polite and reduce the chance of getting
rate-limited or blocked.

IMPORTANT:
- No LinkedIn account / cookies needed for this endpoint.
- LinkedIn still applies anti-bot / rate-limit measures to this endpoint,
  even without login. Keep delays reasonable; don't hammer it.
- This is unofficial use of a public endpoint, not an official API.
  It may break if LinkedIn changes their markup, and heavy/automated use
  may be against LinkedIn's Terms of Service - use responsibly and at
  your own risk.

Usage:
    python -m backend.scripts.linkedin_israel_jobs
    python -m backend.scripts.linkedin_israel_jobs --keywords "Python Developer" --hours 3
"""
from __future__ import annotations

import argparse
import csv
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
RESULTS_PER_PAGE = 25  # LinkedIn's guest API pages in chunks of 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    posted_text: Optional[str]
    job_url: str
    company_url: Optional[str]
    description: Optional[str] = None
    exact_posted_text: Optional[str] = None
    applicants_text: Optional[str] = None
    seniority_level: Optional[str] = None
    employment_type: Optional[str] = None
    job_function: Optional[str] = None
    industries: Optional[str] = None
    company_logo_url: Optional[str] = None


def clean_applicants(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    text = text.strip()
    # Check if it represents less than 25 applicants (either English or Hebrew versions)
    if "first 25" in text.lower() or "25 הראשונים" in text:
        return "< 25"
    # Find any numeric value
    match = re.search(r'(\d+)', text)
    if match:
        return match.group(1)
    return text


def fetch_job_details(session: requests.Session, job: JobListing, delay: float = 2.0) -> None:
    """Fetch job details from the job_url and populate description, exact_posted_text, applicants_text, criteria, and logo."""
    # Force www instead of il subdomain to ensure English responses
    target_url = job.job_url.replace("il.linkedin.com", "www.linkedin.com")
    print(f"Fetching details for: {job.title} @ {job.company}...")
    try:
        resp = session.get(target_url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 1. Parse description
            desc_el = soup.select_one(".show-more-less-html__markup")
            if desc_el:
                job.description = desc_el.get_text(separator="\n", strip=True)
            
            # 2. Parse exact posted time text
            posted_el = soup.select_one(".posted-time-ago__text")
            if posted_el:
                job.exact_posted_text = posted_el.get_text(strip=True)
            
            # 3. Parse applicants count
            applicants_el = soup.select_one(".num-applicants__figure, .num-applicants__caption")
            if applicants_el:
                job.applicants_text = clean_applicants(applicants_el.get_text(strip=True))
                
            # 4. Parse job criteria (Seniority, Employment type, Function, Industries)
            criteria_items = soup.select(".description__job-criteria-item")
            for item in criteria_items:
                subheader = item.select_one(".description__job-criteria-subheader")
                val_el = item.select_one(".description__job-criteria-text")
                if subheader and val_el:
                    sh_txt = subheader.get_text(strip=True).lower()
                    val_txt = val_el.get_text(strip=True)
                    if "seniority" in sh_txt:
                        job.seniority_level = val_txt
                    elif "employment" in sh_txt:
                        job.employment_type = val_txt
                    elif "function" in sh_txt:
                        job.job_function = val_txt
                    elif "industries" in sh_txt:
                        job.industries = val_txt

            # 5. Parse company logo image URL
            logo_el = soup.select_one(".contextual-sign-in-modal__img")
            if logo_el:
                job.company_logo_url = logo_el.get("src") or logo_el.get("data-delayed-url")
            else:
                for img in soup.find_all("img"):
                    src = img.get("src") or img.get("data-delayed-url") or ""
                    classes = img.get("class", [])
                    classes_str = " ".join(classes) if classes else ""
                    if "company-logo" in src or "company-logo" in classes_str:
                        job.company_logo_url = src
                        break
        elif resp.status_code == 429:
            print("    [!] Rate limited (429) on details fetch. Skipping details.")
            time.sleep(5)
        else:
            print(f"    [!] Failed to fetch details, status code: {resp.status_code}")
    except Exception as e:
        print(f"    [!] Error fetching details: {e}")
    time.sleep(delay)





def build_params(keywords: str, location: str, hours: int, start: int) -> dict:
    """Build query params for the guest jobs API.

    f_TPR uses the format rNNNN where NNNN is seconds. 3 hours = 10800.
    """
    return {
        "keywords": keywords,
        "location": location,
        "f_TPR": f"r{hours * 3600}",
        "start": start,
    }


def fetch_page(session: requests.Session, keywords: str, location: str,
               hours: int, start: int, timeout: int = 15) -> Optional[str]:
    """Fetch one page (25 results) of raw HTML from the guest API."""
    params = build_params(keywords, location, hours, start)
    try:
        resp = session.get(BASE_URL, params=params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as e:
        print(f"  [!] Network error at start={start}: {e}")
        return None

    if resp.status_code == 429:
        print(f"  [!] Rate limited (429) at start={start}. Back off and retry later.")
        return None
    if resp.status_code != 200:
        print(f"  [!] Unexpected status {resp.status_code} at start={start}")
        return None

    return resp.text


def parse_jobs(html: str) -> list[JobListing]:
    """Parse a guest-API HTML fragment into JobListing objects."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[JobListing] = []

    cards = soup.select("li")
    for card in cards:
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link_el:
            continue

        title_el = card.select_one("h3.base-search-card__title, h3")
        company_el = card.select_one("h4.base-search-card__subtitle a, h4 a")
        location_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")

        job_url = link_el.get("href", "").split("?")[0]
        title = title_el.get_text(strip=True) if title_el else "N/A"
        company = company_el.get_text(strip=True) if company_el else "N/A"
        company_url = company_el.get("href") if company_el else None
        location = location_el.get_text(strip=True) if location_el else "N/A"
        posted_text = time_el.get_text(strip=True) if time_el else None

        if job_url:
            jobs.append(JobListing(
                title=title,
                company=company,
                location=location,
                posted_text=posted_text,
                job_url=job_url,
                company_url=company_url,
            ))

    return jobs


def scrape_jobs_in_batches(keywords: str, location: str, hours: int,
                            max_pages: int, batch_size: int,
                            delay_between_requests: float,
                            delay_between_batches: float) -> list[JobListing]:
    """
    Pull job pages in batches.

    max_pages: total number of 25-result pages to fetch overall.
    batch_size: how many pages to fetch per batch before the longer pause.
    """
    all_jobs: list[JobListing] = []
    seen_urls = set()

    session = requests.Session()

    for batch_start_page in range(0, max_pages, batch_size):
        batch_pages = range(batch_start_page, min(batch_start_page + batch_size, max_pages))
        print(f"\n--- Batch: pages {batch_start_page}-{batch_start_page + len(list(batch_pages)) - 1} ---")

        empty_page_seen = False
        for page_num in batch_pages:
            start = page_num * RESULTS_PER_PAGE
            print(f"  Fetching page {page_num} (start={start})...")

            html = fetch_page(session, keywords, location, hours, start)
            if html is None:
                continue

            page_jobs = parse_jobs(html)
            if not page_jobs:
                print("  No more jobs found on this page - stopping early.")
                empty_page_seen = True
                break

            new_count = 0
            for job in page_jobs:
                if job.job_url not in seen_urls:
                    seen_urls.add(job.job_url)
                    all_jobs.append(job)
                    new_count += 1

            print(f"  Got {len(page_jobs)} jobs ({new_count} new).")
            time.sleep(delay_between_requests)

        if empty_page_seen:
            break

        print(f"--- End of batch. Total collected so far: {len(all_jobs)} ---")
        time.sleep(delay_between_batches)

    return all_jobs


def save_to_csv(jobs: list[JobListing], filename: str) -> None:
    if not jobs:
        print("No jobs to save.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(jobs[0]).keys()))
        writer.writeheader()
        for job in jobs:
            writer.writerow(asdict(job))
    print(f"Saved {len(jobs)} jobs to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Scrape recent LinkedIn jobs in Israel (no login).")
    parser.add_argument("--keywords", default="", help="Job keywords, e.g. 'Python Developer'")
    parser.add_argument("--location", default="Israel", help="Location filter")
    parser.add_argument("--hours", type=int, default=3, help="Only jobs posted within this many hours")
    parser.add_argument("--max-pages", type=int, default=8, help="Total 25-result pages to fetch (max)")
    parser.add_argument("--batch-size", type=int, default=2, help="Pages per batch before a longer pause")
    parser.add_argument("--request-delay", type=float, default=2.0, help="Seconds between individual requests")
    parser.add_argument("--batch-delay", type=float, default=6.0, help="Seconds between batches")
    parser.add_argument("--out", default="israel_jobs_last_hours.csv", help="Output CSV filename")
    args = parser.parse_args()

    print(f"Searching '{args.keywords or '(any keywords)'}' in {args.location}, "
          f"posted within the last {args.hours}h, up to {args.max_pages} pages "
          f"in batches of {args.batch_size}...")

    jobs = scrape_jobs_in_batches(
        keywords=args.keywords,
        location=args.location,
        hours=args.hours,
        max_pages=args.max_pages,
        batch_size=args.batch_size,
        delay_between_requests=args.request_delay,
        delay_between_batches=args.batch_delay,
    )

    if jobs:
        print(f"\n--- Fetching details for {len(jobs)} jobs in parallel (with incremental saving) ---")
        
        # Initialize the CSV file with headers
        fieldnames = list(asdict(jobs[0]).keys())
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
        csv_lock = threading.Lock()
        
        def process_job(job_obj, index):
            thread_session = requests.Session()
            fetch_job_details(thread_session, job_obj, delay=args.request_delay)
            
            with csv_lock:
                with open(args.out, "a", newline="", encoding="utf-8") as f_append:
                    writer_append = csv.DictWriter(f_append, fieldnames=fieldnames)
                    writer_append.writerow(asdict(job_obj))
            print(f"  [{index}/{len(jobs)}] Saved: {job_obj.title} @ {job_obj.company}")

        # Use ThreadPoolExecutor to request in parallel (max 4 workers to prevent rate limit)
        max_workers = 4
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_job, job, idx + 1) for idx, job in enumerate(jobs)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in thread execution: {e}")

    print(f"\n=== Done. {len(jobs)} unique jobs found in the last {args.hours}h in {args.location}. ===")
    for job in jobs:
        print(f"- {job.title} @ {job.company} | {job.location} | posted: {job.posted_text} / {job.exact_posted_text} | applicants: {job.applicants_text} | {job.job_url}")


if __name__ == "__main__":
    main()
