"""Preview: try a set of choices on 20 random chunks before applying them (guide, Settings).

It runs the same steps as a scan (search, rerank, MMR, judge, quote check) on a small sample and
stores nothing. The result says how many pairs went to the judge, how many were conflicts, and how
many tokens that took, and scales the tokens to the whole library so an admin can see the cost of a
full scan before committing to it.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk, DocumentVersion
from app.pipeline.embed import embedding_input
from app.pipeline.judge import judge_pair, quotes_verified
from app.providers.base import ChatModel, Embedder, ProviderError, Reranker
from app.retrieval import funnel
from app.retrieval.multi_query import extra_queries
from app.retrieval.search import hybrid_search
from app.services.params import PipelineParams
from app.services.scan import JUDGE_THREADS, load_clause

SAMPLE = 20


def run_preview(
    db: Session,
    workspace_id: uuid.UUID,
    chat: ChatModel,
    reranker: Reranker,
    params: PipelineParams,
    embedder: Embedder | None = None,
    rewriter: ChatModel | None = None,
) -> dict:
    started = time.monotonic()
    ready = (
        select(Chunk)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .where(
            Chunk.workspace_id == workspace_id,
            DocumentVersion.status == "ready",
            Chunk.embedding.is_not(None),
        )
    )
    library = db.scalar(select(func.count()).select_from(ready.subquery())) or 0
    sample = db.scalars(ready.order_by(func.random()).limit(SAMPLE)).all()

    rewrite_tokens = 0
    pairs = {}  # pair key -> (clause A, clause B, source chunk, candidate chunk)
    for chunk in sample:
        text = embedding_input(chunk.context_header, chunk.text, chunk.summary)
        extra = []
        if embedder is not None and params.scan_rewrites:
            extra, spent = extra_queries(rewriter or chat, embedder, text, params.scan_rewrites)
            rewrite_tokens += spent
        hits = hybrid_search(
            db,
            workspace_id,
            text,
            chunk.embedding,
            chunk.version_id,
            params=params,
            extra_queries=extra,
        )
        for hit in funnel.apply_funnel(text, hits, reranker, **params.funnel()):
            if hit["kept"]:
                key = funnel.pair_key(chunk.id, hit["chunk"].id)
                if key not in pairs:
                    pairs[key] = (load_clause(db, chunk), load_clause(db, hit["chunk"]), chunk, hit)

    result = {"clauses": len(sample), "pairs": len(pairs), "conflicts": 0, "possible": 0}
    result.update(unverified=0, failed=0, tokens=0)
    with ThreadPoolExecutor(max_workers=JUDGE_THREADS) as pool:
        futures = [pool.submit(judge_pair, chat, a, b) for a, b, _, _ in pairs.values()]
        for (_, _, source, hit), future in zip(pairs.values(), futures, strict=True):
            try:
                out, tokens = future.result()
            except ProviderError:
                result["failed"] += 1
                continue
            result["tokens"] += tokens
            if out.verdict == "no_conflict":
                continue
            if not quotes_verified(out, source.text, hit["chunk"].text):
                result["unverified"] += 1
            elif out.verdict == "conflict":
                result["conflicts"] += 1
            else:
                result["possible"] += 1
    result["tokens"] += rewrite_tokens  # the rewrites are part of what a scan costs
    per_clause = result["tokens"] / len(sample) if sample else 0
    result["library_chunks"] = library
    result["full_scan_tokens"] = round(per_clause * library)
    result["seconds"] = round(time.monotonic() - started, 1)
    return result
