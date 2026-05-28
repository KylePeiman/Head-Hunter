import logging

from headhunter.utils import parse_llm_json, truncate_text

logger = logging.getLogger(__name__)

RECRUITER_PROMPT = """/no_think
You are a recruiter with 30 seconds to review a resume.
You care about: relevant titles, years of experience, recognizable companies, and career trajectory.
Output JSON with exactly these fields:
- pass: bool
- reasoning: one sentence string
Output only the JSON object, nothing else.

Resume:
{resume}

Job Description:
{job_description}"""


def run_recruiter(llm, resume: str, job_description: str, temperature: float) -> dict | None:
    prompt = RECRUITER_PROMPT.format(
        resume=truncate_text(resume, 2000),
        job_description=truncate_text(job_description, 2000),
    )
    try:
        response = llm(
            prompt,
            max_tokens=256,
            temperature=temperature,
            echo=False,
            stop=["\n\n\n"],
        )
        raw = response["choices"][0]["text"]
    except Exception as exc:
        logger.warning("Recruiter LLM call failed: %s", exc)
        return None

    result = parse_llm_json(raw)
    if result is None:
        return None

    result.setdefault("pass", False)
    result.setdefault("reasoning", "")
    return result
