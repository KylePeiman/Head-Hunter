#!/usr/bin/env python3
import logging
import os
import sys
import threading
import time

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
from headhunter.utils import load_config, make_job_hash
from matcher.embedder import Embedder
from output.digest import send_digest
from simulator.pipeline import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("headhunter")


def load_llm(config: dict):
    try:
        from llama_cpp import Llama
    except ImportError:
        logger.error(
            "llama-cpp-python not installed. Install with:\n"
            "  CMAKE_ARGS=\"-DGGML_CUDA=on\" pip install llama-cpp-python"
        )
        sys.exit(1)

    model_path = config["model_path"]
    if not os.path.exists(model_path):
        logger.error(
            "Model file not found: %s\n"
            "Download Qwen3-8B-Q4_K_M.gguf and place it at that path.",
            model_path,
        )
        sys.exit(1)

    logger.info("Loading LLM from %s", model_path)
    return Llama(
        model_path=model_path,
        n_ctx=config.get("llm_context_length", 4096),
        n_gpu_layers=config.get("llm_n_gpu_layers", -1),
        verbose=False,
    )


def crawl_all(config: dict) -> list[dict]:
    all_jobs = []
    for crawler_mod in (adzuna, indeed_rss, remotive, the_muse):
        try:
            jobs = crawler_mod.fetch_jobs(config)
            all_jobs.extend(jobs)
        except Exception as exc:
            logger.warning("Crawler %s failed: %s", crawler_mod.__name__, exc)
    return all_jobs


def run_cycle(config, conn, embedder: Embedder, resume_embedding: list, resume_text: str, llm):
    logger.info("=== Starting crawl cycle ===")

    raw_jobs = crawl_all(config)
    logger.info("Crawlers returned %d total listings", len(raw_jobs))

    new_count = 0
    for job in raw_jobs:
        job_hash = job.get("hash") or make_job_hash(job.get("title", ""), job.get("company", ""))
        job["hash"] = job_hash

        if job_exists(conn, job_hash):
            continue

        # Embed description before inserting
        description = job.get("description") or ""
        if description:
            job["embedding"] = embedder.embed(description)
        else:
            job["embedding"] = embedder.embed(job.get("title", ""))

        insert_job(conn, job)
        new_count += 1

    logger.info("Inserted %d new jobs", new_count)

    # Rank all unprocessed jobs against resume
    pending = get_jobs_without_simulation(conn)
    top_n = config.get("top_n_for_simulation", 20)
    top_jobs = embedder.rank_jobs(resume_embedding, pending, top_n)
    logger.info("Running simulation on top %d/%d unprocessed jobs", len(top_jobs), len(pending))

    if top_jobs and llm is not None:
        results = run_pipeline(llm, resume_text, top_jobs, config)
        for result in results:
            upsert_simulation(conn, result["job_id"], result)
        surfaced = [r for r in results if r.get("surfaced")]
        logger.info("Simulation complete: %d/%d surfaced", len(surfaced), len(results))

        # Send digest if any surfaced
        if surfaced:
            surfaced_jobs = get_surfaced_jobs(conn)
            send_digest(config, surfaced_jobs)
    elif top_jobs and llm is None:
        # No LLM — surface top-N jobs ranked by resume similarity score
        logger.info("No LLM — surfacing %d jobs by similarity score", len(top_jobs))
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

    configure(
        db_path=config.get("db_path", "db/headhunter.db"),
        run_cycle_fn=None,  # set after startup
    )
    host = config.get("flask_host", "127.0.0.1")
    port = config.get("flask_port", 5000)
    debug = config.get("flask_debug", False)
    logger.info("Flask UI running at http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=False)


def main():
    config_path = os.environ.get("HEADHUNTER_CONFIG", "config.yaml")
    config = load_config(config_path)

    # Validate model before heavy initialization (unless --no-llm flag given)
    dry_run = "--no-llm" in sys.argv
    llm = None

    conn = init_db(config["db_path"])
    logger.info("Database initialized at %s", config["db_path"])

    logger.info("Loading embedding model...")
    embedder = Embedder(config.get("embedding_model", "all-MiniLM-L6-v2"))

    resume_path = config.get("resume_path", "resume.txt")
    if not os.path.exists(resume_path):
        logger.error("Resume file not found: %s", resume_path)
        sys.exit(1)
    with open(resume_path, encoding="utf-8", errors="replace") as f:
        resume_text = f.read()
    resume_embedding = embedder.embed(resume_text)
    if resume_embedding is not None:
        logger.info("Resume embedded (%d dims)", len(resume_embedding))
    else:
        logger.info("Resume indexed for TF-IDF ranking")

    if not dry_run:
        llm = load_llm(config)

    def cycle():
        run_cycle(config, conn, embedder, resume_embedding, resume_text, llm)

    # Wire refresh button
    from output.app import configure as configure_flask
    configure_flask(db_path=config["db_path"], run_cycle_fn=cycle)

    # Schedule recurring cycles
    for t in config.get("schedule_times", ["08:00", "18:00"]):
        schedule.every().day.at(t).do(cycle)
        logger.info("Scheduled daily crawl at %s", t)

    # Run once immediately
    cycle()

    # Start Flask in daemon thread
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
