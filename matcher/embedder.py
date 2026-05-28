import logging

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        logger.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        # Vectors are already L2-normalized so cosine sim = dot product
        return float(np.dot(np.array(vec_a), np.array(vec_b)))

    def rank_jobs(
        self,
        resume_embedding: list[float],
        jobs: list[dict],
        top_n: int,
    ) -> list[dict]:
        scored = []
        for job in jobs:
            emb = job.get("embedding")
            if not emb:
                continue
            score = self.cosine_similarity(resume_embedding, emb)
            job = dict(job)
            job["similarity_score"] = score
            scored.append(job)

        scored.sort(key=lambda j: j["similarity_score"], reverse=True)
        return scored[:top_n]
