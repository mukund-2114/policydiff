"""Steps 5 to 7 of the conflict funnel: rerank, drop near-duplicates, name each pair once.

Input is the ~30 hits from `hybrid_search`. Output is the same hits, each with a rerank score and a
`kept` flag. The few that stay `kept` are the pairs the judge will read (S8). The rest are shown
too, so the cut can be inspected.
"""

from app.pipeline.embed import embedding_input
from app.providers.base import Reranker
from app.retrieval.rank import mmr

RELATED_THRESHOLD = 0.5  # rerank score a candidate needs to be worth judging (tuned in the eval)
MAX_RERANKED = 8  # guide step 5
MMR_LAMBDA = 0.8  # the guide says 0.6; at 0.6 the eval lost 2 of 23 partners (D41)
MMR_KEEP = 5


def pair_key(chunk_a, chunk_b) -> str:
    """The same name for (A, B) and (B, A). Chunk ids belong to one version each, so a new version
    of a policy gives new keys and its pairs are judged again, while unchanged pairs are skipped."""
    first, second = sorted((str(chunk_a), str(chunk_b)))
    return f"{first}:{second}"


def apply_funnel(
    source_text: str,
    hits: list[dict],
    reranker: Reranker,
    threshold: float = RELATED_THRESHOLD,
    max_reranked: int = MAX_RERANKED,
    keep: int = MMR_KEEP,
    lam: float = MMR_LAMBDA,
) -> list[dict]:
    """Score every hit against the source text, then keep the related and varied ones.

    Hits come back in their original (RRF) order with `rerank_score` and `kept` added.
    """
    if not hits:
        return []
    docs = [
        embedding_input(h["chunk"].context_header, h["chunk"].text, h["chunk"].summary)
        for h in hits
    ]
    scores = reranker.score(source_text, docs)
    for h, s in zip(hits, scores, strict=True):
        h["rerank_score"], h["kept"] = s, False

    # Related enough, best first, at most `max_reranked`. Then MMR trims near-copies.
    related = sorted(
        (h for h in hits if h["rerank_score"] >= threshold), key=lambda h: -h["rerank_score"]
    )
    related = related[:max_reranked]
    by_id = {h["chunk"].id: h for h in related}
    chosen = mmr(
        {i: h["rerank_score"] for i, h in by_id.items()},
        {i: h["chunk"].embedding for i, h in by_id.items()},
        lam=lam,
        keep=keep,
    )
    for i in chosen:
        by_id[i]["kept"] = True
    return hits
