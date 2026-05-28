import logging
import time
from datetime import datetime, timezone

import requests

from headhunter.utils import make_job_hash, strip_html, truncate_text

logger = logging.getLogger(__name__)

BASE_URL = "https://remotive.com/api/remote-jobs"


def fetch_jobs(config: dict) -> list[dict]:
    cfg = config.get("crawlers", {}).get("remotive", {})
    if not cfg.get("enabled"):
        return []

    job_titles = config.get("job_titles", [])
    delay = config.get("request_delay_seconds", 2.5)

    all_jobs = []
    for title in job_titles:
        try:
            resp = requests.get(
                BASE_URL,
                params={"search": title, "limit": 50},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for raw in data.get("jobs", []):
                job = _normalize(raw)
                if job:
                    all_jobs.append(job)
        except Exception as exc:
            logger.warning("Remotive request failed (title=%r): %s", title, exc)
        time.sleep(delay)

    logger.info("Remotive: fetched %d jobs", len(all_jobs))
    return all_jobs


def _normalize(raw: dict) -> dict | None:
    title = (raw.get("title") or "").strip()
    company = (raw.get("company_name") or "").strip()
    if not title or not company:
        return None

    description = strip_html(raw.get("description") or "")
    description = truncate_text(description, 3000)

    location = raw.get("candidate_required_location") or "Worldwide"

    posted_raw = raw.get("publication_date", "")
    try:
        posted_at = datetime.fromisoformat(posted_raw.rstrip("Z")).replace(tzinfo=timezone.utc).isoformat()
    except (ValueError, AttributeError):
        posted_at = ""

    return {
        "hash": make_job_hash(title, company),
        "title": title,
        "company": company,
        "location": location,
        "remote": True,
        "description": description,
        "url": raw.get("url", ""),
        "source": "remotive",
        "posted_at": posted_at,
        "embedding": None,
    }
