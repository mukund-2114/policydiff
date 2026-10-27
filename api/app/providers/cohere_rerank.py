"""Cohere Rerank: a hosted cross-encoder. One call scores every candidate for a clause.

Clause text is sent to Cohere, so egress.allow_cloud must be true (see registry.check_egress).
"""

import httpx

from app.providers.base import ProviderError

URL = "https://api.cohere.com/v2/rerank"


class CohereReranker:
    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise ProviderError("COHERE_API_KEY is not set")
        self.model = model
        self._key = api_key

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        r = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self.model, "query": query, "documents": docs, "top_n": len(docs)},
            timeout=30,
        )
        if r.status_code != 200:
            raise ProviderError(f"Cohere rerank failed ({r.status_code}): {r.text[:200]}")
        # Results come back best first with the index of the document they belong to.
        scores = [0.0] * len(docs)
        for item in r.json()["results"]:
            scores[item["index"]] = item["relevance_score"]
        return scores
