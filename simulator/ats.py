import logging
import re

import requests

from headhunter.utils import parse_llm_json, truncate_text

logger = logging.getLogger(__name__)

ATS_PROMPT = """You are an ATS system. You do not reason — you check for keyword matches only.
Given this job description and resume, output JSON with exactly these fields:
- pass: bool
- matched_keywords: list of strings
- missing_keywords: list of strings
Do not infer or assume skills. Only match exact or near-exact terms.
Output only the JSON object, nothing else.

Resume:
{resume}

Job Description:
{job_description}"""


def run_ats(llm_url: str, resume: str, job_description: str, temperature: float) -> dict | None:
    prompt = ATS_PROMPT.format(
        resume=truncate_text(resume, 2000),
        job_description=truncate_text(job_description, 2000),
    )
    try:
        resp = requests.post(
            f"{llm_url}/completion",
            json={"prompt": prompt, "max_tokens": 512, "temperature": temperature, "stop": ["\n\n\n"]},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("content", "")
    except Exception as exc:
        logger.warning("ATS LLM call failed: %s", exc)
        return None

    result = parse_llm_json(raw)
    if result is None:
        return None

    result.setdefault("pass", False)
    result.setdefault("matched_keywords", [])
    result.setdefault("missing_keywords", [])
    return result
