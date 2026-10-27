"""Steps 3 and 4 of the conflict funnel: search by meaning, search by words, merge with RRF.

These functions talk to the database. The merging maths is in `rank.py`, where tests reach it.
Only chunks of `ready` versions are searched, so superseded versions never come back (D38).
"""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentVersion
from app.retrieval.rank import rrf

TOP_EACH = 25  # guide step 3: top 25 from each search
TOP_FUSED = 30  # guide step 4: keep 30 after RRF


def _scope(q, workspace_id: uuid.UUID, exclude_version_id: uuid.UUID | None):
    """Only current chunks of this workspace, and never the version the query came from."""
    q = q.join(DocumentVersion, DocumentVersion.id == Chunk.version_id).where(
        Chunk.workspace_id == workspace_id, DocumentVersion.status == "ready"
    )
    if exclude_version_id:
        q = q.where(Chunk.version_id != exclude_version_id)
    return q


def vector_search(db, workspace_id, query_vector, exclude_version_id=None, limit=TOP_EACH):
    """Chunk ids nearest in meaning, best first (cosine distance, the HNSW index)."""
    q = select(Chunk.id).where(Chunk.embedding.is_not(None))
    q = _scope(q, workspace_id, exclude_version_id)
    return list(db.scalars(q.order_by(Chunk.embedding.cosine_distance(query_vector)).limit(limit)))


def or_query(text: str) -> str:
    """Turn free text into a tsquery that matches any of its words: 'a | b | c'.

    `plainto_tsquery` would need every word to be present, which almost never happens when the
    query is a whole clause. With OR, a chunk matching more words ranks higher instead.
    Only letters and digits are kept, so punctuation in a clause cannot break the query syntax.
    """
    words = dict.fromkeys(re.findall(r"[A-Za-z0-9]+", text.lower()))  # unique, in order
    return " | ".join(words)


def keyword_search(db, workspace_id, query_text, exclude_version_id=None, limit=TOP_EACH):
    """Chunk ids sharing the most words with the query, best first (the tsvector GIN index)."""
    tsquery_text = or_query(query_text)
    if not tsquery_text:
        return []
    tsquery = func.to_tsquery("english", tsquery_text)
    q = select(Chunk.id).where(Chunk.tsv.op("@@")(tsquery))
    q = _scope(q, workspace_id, exclude_version_id)
    return list(db.scalars(q.order_by(func.ts_rank_cd(Chunk.tsv, tsquery).desc()).limit(limit)))


def hybrid_search(
    db: Session,
    workspace_id: uuid.UUID,
    query_text: str,
    query_vector: list[float],
    exclude_version_id: uuid.UUID | None = None,
) -> list[dict]:
    """Both searches, merged with RRF. Returns hits best first with where each one was found."""
    by_meaning = vector_search(db, workspace_id, query_vector, exclude_version_id)
    by_words = keyword_search(db, workspace_id, query_text, exclude_version_id)
    fused = rrf([by_meaning, by_words], top=TOP_FUSED)

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
