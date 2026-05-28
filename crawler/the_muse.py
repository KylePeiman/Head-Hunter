import logging
import time
from datetime import datetime, timezone

import requests

from headhunter.utils import make_job_hash, strip_html, truncate_text

logger = logging.getLogger(__name__)

BASE_URL = "https://www.themuse.com/api/public/jobs"


def fetch_jobs(config: dict) -> list[dict]:
    cfg = config.get("crawlers", {}).get("the_muse", {})
    if not cfg.get("enabled"):
        return []

    job_titles = config.get("job_titles", [])
    api_key = cfg.get("api_key", "")
    delay = config.get("request_delay_seconds", 2.5)

    all_jobs = []
    for title in job_titles:
        for page in range(1, 6):
            params = {"category": title, "page": page, "descended": "true"}
            if api_key:
                params["api_key"] = api_key
            try:
                resp = requests.get(BASE_URL, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break
                for raw in results:
                    job = _normalize(raw)
                    if job:
                        all_jobs.append(job)
            except Exception as exc:
                logger.warning("The Muse request failed (title=%r, page=%d): %s", title, page, exc)
                break
            time.sleep(delay)

    logger.info("The Muse: fetched %d jobs", len(all_jobs))
    return all_jobs


def _normalize(raw: dict) -> dict | None:
    title = (raw.get("name") or "").strip()
    company_data = raw.get("company") or {}
    company = (company_data.get("name") or "").strip()
    if not title or not company:
        return None

    description = strip_html(raw.get("contents") or "")
    description = truncate_text(description, 3000)

    locations = raw.get("locations") or []
    location = locations[0].get("name", "") if locations else ""
    remote_flag = any("remote" in (loc.get("name", "") or "").lower() for loc in locations)

    posted_raw = raw.get("publication_date", "")
    try:
        posted_at = datetime.fromisoformat(posted_raw.rstrip("Z")).replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        posted_at = ""

    refs = raw.get("refs") or {}
    url = refs.get("landing_page", "")

    return {
        "hash": make_job_hash(title, company),
        "title": title,
        "company": company,
        "location": location,
        "remote": remote_flag,
        "description": description,
        "url": url,
        "source": "the_muse",
        "posted_at": posted_at,
        "embedding": None,
    }
