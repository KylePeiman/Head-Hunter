import logging
import time
from datetime import datetime, timezone

import feedparser

from headhunter.utils import make_job_hash, strip_html, truncate_text

logger = logging.getLogger(__name__)

BASE_URL = "https://www.indeed.com/rss"


def fetch_jobs(config: dict) -> list[dict]:
    cfg = config.get("crawlers", {}).get("indeed_rss", {})
    if not cfg.get("enabled"):
        return []

    job_titles = config.get("job_titles", [])
    location = config.get("location", "")
    delay = config.get("request_delay_seconds", 2.5)

    all_jobs = []
    for title in job_titles:
        url = f"{BASE_URL}?q={requests_encode(title)}&l={requests_encode(location)}"
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                job = _normalize(entry)
                if job:
                    all_jobs.append(job)
        except Exception as exc:
            logger.warning("Indeed RSS request failed (title=%r): %s", title, exc)
        time.sleep(delay)

    logger.info("Indeed RSS: fetched %d jobs", len(all_jobs))
    return all_jobs


def requests_encode(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


def _normalize(entry) -> dict | None:
    raw_title = (getattr(entry, "title", "") or "").strip()
    if not raw_title:
        return None

    # Indeed RSS titles are typically "Job Title - Company Name"
    if " - " in raw_title:
        parts = raw_title.rsplit(" - ", 1)
        title = parts[0].strip()
        company = parts[1].strip()
    else:
        title = raw_title
        company = "Unknown"

    if not title:
        return None

    description = strip_html(getattr(entry, "summary", "") or "")
    description = truncate_text(description, 3000)

    url = getattr(entry, "link", "")

    published = getattr(entry, "published_parsed", None)
    if published:
        try:
            posted_at = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
        except (TypeError, ValueError):
            posted_at = ""
    else:
        posted_at = ""

    remote_flag = "remote" in (description + title).lower()

    return {
        "hash": make_job_hash(title, company),
        "title": title,
        "company": company,
        "location": "",
        "remote": remote_flag,
        "description": description,
        "url": url,
        "source": "indeed_rss",
        "posted_at": posted_at,
        "embedding": None,
    }
