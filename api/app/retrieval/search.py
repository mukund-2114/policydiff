"""Steps 3 and 4 of the conflict funnel: search by meaning, search by words, merge with RRF.
The word search ranks with BM25 (`bm25.py`), and extra queries from multi-query join the merge.

These functions talk to the database. The merging maths is in `rank.py`, where tests reach it.
Only chunks of `ready` versions are searched, so superseded versions never come back (D38).
"""

import re
import uuid
from datetime import date

from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentVersion
from app.retrieval import bm25
from app.retrieval.rank import rrf
from app.services.params import PipelineParams


def _scope(
    q, workspace_id: uuid.UUID, exclude_version_id: uuid.UUID | None, as_of: date | None = None
):
    """Only current chunks of this workspace, and never the version the query came from.

    With `as_of`, "current" means whichever versions were in effect on that day, so a version that
    has since been superseded is searched, and one that starts later is not (guide, Q&A mode).
    """
    q = q.join(DocumentVersion, DocumentVersion.id == Chunk.version_id).where(
        Chunk.workspace_id == workspace_id
    )
    if as_of is None:
        q = q.where(DocumentVersion.status == "ready")
    else:
        q = q.where(
            DocumentVersion.status.in_(["ready", "superseded"]),
            or_(DocumentVersion.effective_from.is_(None), DocumentVersion.effective_from <= as_of),
            or_(DocumentVersion.effective_to.is_(None), DocumentVersion.effective_to > as_of),
        )
    if exclude_version_id:
        q = q.where(Chunk.version_id != exclude_version_id)
    return q


def vector_search(db, workspace_id, query_vector, exclude_version_id=None, limit=25, as_of=None):
    """Chunk ids nearest in meaning, best first (cosine distance, the HNSW index)."""
    q = select(Chunk.id).where(Chunk.embedding.is_not(None))
    q = _scope(q, workspace_id, exclude_version_id, as_of)
    return list(db.scalars(q.order_by(Chunk.embedding.cosine_distance(query_vector)).limit(limit)))


def or_query(text: str) -> str:
    """Turn free text into a tsquery that matches any of its words: 'a | b | c'.

    `plainto_tsquery` would need every word to be present, which almost never happens when the
    query is a whole clause. With OR, a chunk matching more words ranks higher instead.
    Only letters and digits are kept, so punctuation in a clause cannot break the query syntax.
    """
    words = dict.fromkeys(re.findall(r"[A-Za-z0-9]+", text.lower()))  # unique, in order
    return " | ".join(words)


def keyword_search(
    db,
    workspace_id,
    query_text,
    exclude_version_id=None,
    limit=25,
    as_of=None,
    params=None,
    stats=None,
):
    """Chunk ids sharing the most words with the query, best first.

    Postgres finds the chunks that match any word (the tsvector GIN index) and hands the best
    `bm25.POOL` of them to BM25, which re-scores them and keeps the top `limit`.
    """
    tsquery_text = or_query(query_text)
    if not tsquery_text or limit <= 0:  # a limit of 0 switches keyword search off
        return []
    p = params or PipelineParams()
    tsquery = func.to_tsquery("english", tsquery_text)
    q = select(Chunk.id, Chunk.tsv.cast(Text)).where(Chunk.tsv.op("@@")(tsquery))
    q = _scope(q, workspace_id, exclude_version_id, as_of)
    rows = db.execute(q.order_by(func.ts_rank_cd(Chunk.tsv, tsquery).desc()).limit(bm25.POOL)).all()
    pool = {chunk_id: bm25.parse_tsvector(tsv) for chunk_id, tsv in rows}
    stats = stats or bm25.load_stats(db, workspace_id)
    terms = bm25.query_terms(db, query_text)
    return bm25.rank(terms, pool, stats, p.bm25_k1, p.bm25_b, limit)


def hybrid_search(
    db: Session,
    workspace_id: uuid.UUID,
    query_text: str,
    query_vector: list[float],
    exclude_version_id: uuid.UUID | None = None,
    as_of: date | None = None,
    params: PipelineParams | None = None,
    extra_queries: list[tuple[str, list[float]]] | None = None,
) -> list[dict]:
    """Both searches, merged with RRF. Returns hits best first with where each one was found.

    `params` carries the admin's numbers. Left out, the defaults are used, so tests and evals run
    the same way every time; callers that serve users pass `get_params()`.
    `extra_queries` are rewrites of the query (text and vector, see multi_query.py). Each one gets
    its own search by meaning and by words, and all the lists go into the one RRF merge. The ranks
    reported for each hit are those of the original query.
    """
    p = params or PipelineParams()
    stats = bm25.load_stats(db, workspace_id) if p.keyword_results > 0 else None
    queries = [(query_text, query_vector), *(extra_queries or [])]
    lists, by_meaning, by_words = [], [], []
    for i, (text, vector) in enumerate(queries):
        meaning = vector_search(
            db, workspace_id, vector, exclude_version_id, limit=p.vector_results, as_of=as_of
        )
        words = keyword_search(
            db,
            workspace_id,
            text,
            exclude_version_id,
            limit=p.keyword_results,
            as_of=as_of,
            params=p,
            stats=stats,
        )
        lists += [meaning, words]
        if i == 0:
            by_meaning, by_words = meaning, words
    fused = rrf(lists, k=p.rrf_k, top=p.fused_keep)

    ids = [chunk_id for chunk_id, _ in fused]
    rows = db.execute(
        select(Chunk, Document.title, DocumentVersion.version_label)
        .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(Chunk.id.in_(ids))
    ).all()
    found = {c.id: (c, title, label) for c, title, label in rows}
    return [
        dict(
            chunk=found[chunk_id][0],
            title=found[chunk_id][1],
            version_label=found[chunk_id][2],
            score=score,
            vector_rank=by_meaning.index(chunk_id) + 1 if chunk_id in by_meaning else None,
            keyword_rank=by_words.index(chunk_id) + 1 if chunk_id in by_words else None,
        )
        for chunk_id, score in fused
    ]
