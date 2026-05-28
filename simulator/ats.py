import logging

from headhunter.utils import parse_llm_json, truncate_text

logger = logging.getLogger(__name__)

ATS_PROMPT = """/no_think
You are an ATS system. You do not reason — you check for keyword matches only.
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


def run_ats(llm, resume: str, job_description: str, temperature: float) -> dict | None:
    prompt = ATS_PROMPT.format(
        resume=truncate_text(resume, 2000),
        job_description=truncate_text(job_description, 2000),
    )
    try:
        response = llm(
            prompt,
            max_tokens=512,
            temperature=temperature,
            echo=False,
            stop=["\n\n\n"],
        )
        raw = response["choices"][0]["text"]
    except Exception as exc:
        logger.warning("ATS LLM call failed: %s", exc)
        return None

    result = parse_llm_json(raw)
    if result is None:
        return None

    # Ensure required keys exist with safe defaults
    result.setdefault("pass", False)
    result.setdefault("matched_keywords", [])
    result.setdefault("missing_keywords", [])
    return result
