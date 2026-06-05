import logging
import random
from collections import Counter

from simulator.ats import run_ats
from simulator.recruiter import run_recruiter

logger = logging.getLogger(__name__)


def aggregate_missing_keywords(all_missing: list[list[str]], top_n: int = 5) -> list[str]:
    flat = [kw.lower().strip() for sublist in all_missing for kw in sublist if kw]
    counter = Counter(flat)
    return [kw for kw, _ in counter.most_common(top_n)]


def simulate_job(
    llm_url: str,
    resume: str,
    job: dict,
    rounds: int = 5,
    temp_min: float = 0.5,
    temp_max: float = 0.7,
    surface_threshold: int = 3,
) -> dict:
    description = job.get("description", "")
    ats_passes = 0
    recruiter_passes = 0
    all_missing_keywords: list[list[str]] = []
    recruiter_reasonings: list[str] = []

    for _ in range(rounds):
        temp = random.uniform(temp_min, temp_max)

        ats_result = run_ats(llm_url, resume, description, temp)
        if ats_result is None:
            logger.debug("ATS returned None for job_id=%s", job.get("id"))
            continue

        if ats_result.get("pass"):
            ats_passes += 1
            missing = ats_result.get("missing_keywords") or []
            all_missing_keywords.append(missing)

            rec_result = run_recruiter(llm_url, resume, description, temp)
            if rec_result is None:
                logger.debug("Recruiter returned None for job_id=%s", job.get("id"))
                continue

            reasoning = rec_result.get("reasoning", "")
            if reasoning:
                recruiter_reasonings.append(reasoning)

            if rec_result.get("pass"):
                recruiter_passes += 1
        else:
            missing = ats_result.get("missing_keywords") or []
            all_missing_keywords.append(missing)

    surfaced = recruiter_passes >= surface_threshold
    pass_rate = recruiter_passes / rounds if rounds > 0 else 0.0
    ats_pass_rate = ats_passes / rounds if rounds > 0 else 0.0
    common_missing = aggregate_missing_keywords(all_missing_keywords)
    sample_reasoning = recruiter_reasonings[0] if recruiter_reasonings else ""

    logger.info(
        "Simulated job_id=%s title=%r: surfaced=%s pass_rate=%.2f ats_pass_rate=%.2f",
        job.get("id"),
        job.get("title"),
        surfaced,
        pass_rate,
        ats_pass_rate,
    )

    return {
        "job_id": job.get("id"),
        "surfaced": surfaced,
        "pass_rate": pass_rate,
        "ats_pass_rate": ats_pass_rate,
        "common_missing_keywords": common_missing,
        "sample_recruiter_reasoning": sample_reasoning,
    }


def run_pipeline(llm_url: str, resume: str, jobs: list[dict], config: dict) -> list[dict]:
    rounds = config.get("simulation_rounds", 5)
    temp_min = config.get("temperature_min", 0.5)
    temp_max = config.get("temperature_max", 0.7)
    threshold = config.get("surface_threshold", 3)

    results = []
    total = len(jobs)
    for i, job in enumerate(jobs, 1):
        logger.info("Simulating job %d/%d: %s at %s", i, total, job.get("title"), job.get("company"))
        result = simulate_job(
            llm_url=llm_url,
            resume=resume,
            job=job,
            rounds=rounds,
            temp_min=temp_min,
            temp_max=temp_max,
            surface_threshold=threshold,
        )
        results.append(result)

    return results
