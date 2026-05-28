import logging
import time
from datetime import datetime, timezone

import requests

from headhunter.utils import make_job_hash, strip_html, truncate_text

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def fetch_jobs(config: dict) -> list[dict]:
    cfg = config.get("crawlers", {}).get("adzuna", {})
    if not cfg.get("enabled"):
        return []

    api_id = cfg.get("api_id", "")
    api_key = cfg.get("api_key", "")
    if not api_id or api_id == "YOUR_ADZUNA_APP_ID":
        logger.warning("Adzuna API credentials not configured — skipping")
        return []

    country = cfg.get("country", "us")
    results_per_page = cfg.get("results_per_page", 50)
    max_pages = cfg.get("max_pages", 1)
    location = config.get("location", "")
    job_titles = config.get("job_titles", [])
    delay = config.get("request_delay_seconds", 2.5)

    all_jobs = []
    for title in job_titles:
        for page in range(1, max_pages + 1):
            url = BASE_URL.format(country=country, page=page)
            params = {
                "app_id": api_id,
                "app_key": api_key,
                "what": title,
                "where": location,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            }
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for raw in data.get("results", []):
                    job = _normalize(raw)
                    if job:
                        all_jobs.append(job)
            except Exception as exc:
                logger.warning("Adzuna request failed (title=%r, page=%d): %s", title, page, exc)
            time.sleep(delay)

    logger.info("Adzuna: fetched %d jobs", len(all_jobs))
    return all_jobs


def _normalize(raw: dict) -> dict | None:
    title = (raw.get("title") or "").strip()
    company = (raw.get("company", {}) or {}).get("display_name", "").strip()
    if not title or not company:
        return None

    description = strip_html(raw.get("description") or "")
    description = truncate_text(description, 3000)

    location_parts = raw.get("location", {}) or {}
    location = location_parts.get("display_name", "")

    posted_raw = raw.get("created", "")
    try:
        posted_at = datetime.fromisoformat(posted_raw.rstrip("Z")).replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        posted_at = ""

    remote_flag = "remote" in (description + title + location).lower()

    return {
        "hash": make_job_hash(title, company),
        "title": title,
        "company": company,
        "location": location,
        "remote": remote_flag,
        "description": description,
        "url": raw.get("redirect_url", ""),
        "source": "adzuna",
        "posted_at": posted_at,
        "embedding": None,
    }
