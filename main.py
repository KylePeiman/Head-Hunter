#!/usr/bin/env python3
import logging
import os
import sys
import threading
import time

import requests
import schedule

from crawler import adzuna, indeed_rss, remotive, the_muse
from db.database import (
    close_db,
    get_jobs_without_simulation,
    get_surfaced_jobs,
    init_db,
    insert_job,
    job_exists,
    update_job_embedding,
    upsert_simulation,
)
from headhunter.utils import load_config, make_job_hash, read_resume
from matcher.embedder import Embedder
from output.digest import send_digest
from simulator.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("headhunter")


def check_llm_server(url: str) -> bool:
    try:
        resp = requests.get(f"{url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def crawl_all(config: dict) -> list[dict]:
    all_jobs = []
    for crawler_mod in (adzuna, indeed_rss, remotive, the_muse):
        try:
            jobs = crawler_mod.fetch_jobs(config)
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.warning("Crawler %s failed: %s", crawler_mod.__name__, exc)
    return all_jobs


def run_cycle(config, conn, embedder: Embedder, resume_embedding: list, resume_text: str, llm_url: str | None):
    logger.info("=== Starting crawl cycle ===")

    raw_jobs = crawl_all(config)
    logger.info("Crawlers returned %d total listings", len(raw_jobs))

    new_count = 0
    for job in raw_jobs:
        job_hash = job.get("hash") or make_job_hash(job.get("title", ""), job.get("company", ""))
        job["hash"] = job_hash

        if job_exists(conn, job_hash):
            continue

        description = job.get("description") or ""
        job["embedding"] = embedder.embed(description or job.get("title", ""))
        insert_job(conn, job)
        new_count += 1

    logger.info("Inserted %d new jobs", new_count)

    pending = get_jobs_without_simulation(conn)
    top_n = config.get("top_n_for_simulation", 20)
    top_jobs = embedder.rank_jobs(resume_embedding, pending, top_n)
    logger.info("Running simulation on top %d/%d unprocessed jobs", len(top_jobs), len(pending))

    if top_jobs and llm_url is not None:
        results = run_pipeline(llm_url, resume_text, top_jobs, config)
        for result in results:
            upsert_simulation(conn, result["job_id"], result)
        surfaced = [r for r in results if r.get("surfaced")]
        logger.info("Simulation complete: %d/%d surfaced", len(surfaced), len(results))

        if surfaced:
            send_digest(config, get_surfaced_jobs(conn))
    elif top_jobs:
        logger.info("No LLM server — surfacing %d jobs by similarity score", len(top_jobs))
        for job in top_jobs:
            score = job.get("similarity_score", 0.0)
            upsert_simulation(conn, job["id"], {
                "surfaced": True,
                "pass_rate": score,
                "ats_pass_rate": score,
                "common_missing_keywords": [],
                "sample_recruiter_reasoning": "Ranked by resume similarity (no LLM simulation)",
            })
        send_digest(config, get_surfaced_jobs(conn))

    logger.info("=== Cycle complete ===")


def run_server(config: dict) -> None:
    from output.app import app, configure

    configure(db_path=config.get("db_path", "db/headhunter.db"))
    host = config.get("flask_host", "127.0.0.1")
    port = config.get("flask_port", 5000)
    debug = config.get("flask_debug", False)
    logger.info("Flask UI running at http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def main():
    config_path = os.environ.get("HEADHUNTER_CONFIG", "config.yaml")
    config = load_config(config_path)

    conn = init_db(config["db_path"])
    logger.info("Database initialized at %s", config["db_path"])

    logger.info("Loading embedding model...")
    embedder = Embedder(config.get("embedding_model", "all-MiniLM-L6-v2"))

    resume_path = config.get("resume_path", "resume.txt")
    if not os.path.exists(resume_path):
        logger.error("Resume file not found: %s", resume_path)
        sys.exit(1)
    resume_text = read_resume(resume_path)
    resume_embedding = embedder.embed(resume_text)
    if resume_embedding is not None:
        logger.info("Resume embedded (%d dims)", len(resume_embedding))
    else:
        logger.info("Resume indexed for TF-IDF ranking")

    # Check LLM server availability
    llm_url: str | None = None
    if "--no-llm" not in sys.argv:
        url = config.get("llama_server_url", "http://localhost:8081")
        if check_llm_server(url):
            llm_url = url
            logger.info("LLM server reachable at %s", url)
        else:
            logger.warning(
                "LLM server not reachable at %s — running in similarity-only mode. "
                "Start your llama.cpp server or use --no-llm to suppress this warning.",
                url,
            )

    def cycle():
        run_cycle(config, conn, embedder, resume_embedding, resume_text, llm_url)

    from output.app import configure as configure_flask
    configure_flask(db_path=config["db_path"], run_cycle_fn=cycle)

    for t in config.get("schedule_times", ["08:00", "18:00"]):
        schedule.every().day.at(t).do(cycle)
        logger.info("Scheduled daily crawl at %s", t)

    cycle()

    server_thread = threading.Thread(target=run_server, args=(config,), daemon=True)
    server_thread.start()

    logger.info("Scheduler running. Press Ctrl+C to exit.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Shutting down.")
        close_db(conn)


if __name__ == "__main__":
    main()
