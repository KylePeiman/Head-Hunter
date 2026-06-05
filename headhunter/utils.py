import hashlib
import json
import logging
import re

import yaml

logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_job_hash(title: str, company: str) -> str:
    key = f"{title.lower().strip()}{company.lower().strip()}"
    return hashlib.md5(key.encode()).hexdigest()


def parse_llm_json(raw: str) -> dict | None:
    # Strip <think>...</think> blocks (Qwen3 chain-of-thought)
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip().strip("`").strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Failed to parse LLM JSON. Raw output: %r", raw)
        return None
    # Normalize string booleans
    for key in ("pass",):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].lower() == "true"
    return data


def truncate_text(text: str, max_chars: int = 3000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def read_resume(path: str) -> str:
    if path.lower().endswith(".docx"):
        from docx import Document
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return open(path, encoding="utf-8", errors="replace").read()


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
