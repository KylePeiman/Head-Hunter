import logging

import numpy as np

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._resume_text: str = ""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", model_name)
            self.model = SentenceTransformer(model_name)
            self.mode = "sentence_transformer"
        except Exception as exc:
            logger.warning("sentence-transformers unavailable (%s) — falling back to TF-IDF", exc)
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401 (validate import)
            self.mode = "tfidf"

    def embed(self, text: str) -> list[float] | None:
        if self.mode == "tfidf":
            # Store the first call (always the resume) for use in rank_jobs
            if not self._resume_text:
                self._resume_text = text
            return None
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        return float(np.dot(np.array(vec_a), np.array(vec_b)))

    def rank_jobs(
        self,
        resume_embedding: list[float] | None,
        jobs: list[dict],
        top_n: int,
    ) -> list[dict]:
        if self.mode == "tfidf":
            return self._rank_tfidf(jobs, top_n)

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

    def _rank_tfidf(self, jobs: list[dict], top_n: int) -> list[dict]:
        if not jobs:
            return []
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as sk_cosine

        if not self._resume_text:
            logger.warning("Resume text not set for TF-IDF ranking — results may be poor")

        job_texts = [j.get("description") or j.get("title", "") for j in jobs]
        corpus = [self._resume_text] + job_texts

        vectorizer = TfidfVectorizer(stop_words="english", max_features=10000, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(corpus)

        resume_vec = matrix[0]
        job_matrix = matrix[1:]
        scores = sk_cosine(resume_vec, job_matrix)[0]

        scored = []
        for job, score in zip(jobs, scores):
            job = dict(job)
            job["similarity_score"] = float(score)
            scored.append(job)

        scored.sort(key=lambda j: j["similarity_score"], reverse=True)
        return scored[:top_n]
