"""Two pure functions of the retrieval funnel: reciprocal rank fusion and MMR.

"Pure" means they only look at their arguments. No database, no network, so the unit tests can feed
them small lists and check the answer by hand. Written by hand on purpose (D4).
"""

import math
from collections.abc import Hashable, Sequence


def rrf(rankings: Sequence[Sequence[Hashable]], k: int = 60, top: int = 30):
    """Merge several ranked lists into one. Returns [(id, score)], best first.

    Each list gives an id the score 1 / (k + rank), rank starting at 1, and the scores are added.
    An id near the top of two lists beats an id first in one list and missing from the other.
    Only the positions matter, never the raw scores, so a vector distance and a keyword score can
    be mixed even though they are on different scales. k = 60 is the usual value: a large k makes
    the first places count less against the rest.
    """
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    # Sorting by (-score) keeps ties in the order the ids first appeared, because sort is stable.
    ordered = sorted(scores.items(), key=lambda pair: -pair[1])
    return ordered[:top]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """How alike two vectors point, from -1 to 1. A zero vector is alike to nothing (0)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def mmr(
    relevance: dict[Hashable, float],
    vectors: dict[Hashable, Sequence[float]],
    lam: float = 0.6,
    keep: int = 5,
) -> list[Hashable]:
    """Pick `keep` ids that are relevant and different from each other (maximal marginal relevance).

    Starts with the most relevant id. Each next pick maximises
        lam * relevance - (1 - lam) * (largest similarity to anything already picked).
    lam = 1 is plain top-k; lower values push harder for variety. The same rule restated in three
    places is only worth one judge call, so the copies lose to a different candidate.
    `relevance` should be on a 0 to 1 scale (the reranker score) so it is comparable with cosine.
    """
    left = list(relevance)
    picked: list[Hashable] = []
    while left and len(picked) < keep:

        def value(item: Hashable) -> float:
            overlap = max((cosine(vectors[item], vectors[p]) for p in picked), default=0.0)
            return lam * relevance[item] - (1 - lam) * overlap

        best = max(left, key=value)  # max keeps the first of equals, so ties follow input order
        picked.append(best)
        left.remove(best)
    return picked
