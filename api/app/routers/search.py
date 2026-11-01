"""Try the funnel by hand: hybrid search, then rerank and MMR. The scan (S8) runs the same steps."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db.session import get_db
from app.models import Chunk, User
from app.pipeline.embed import embedding_input
from app.providers.base import ProviderError
from app.providers.registry import get_embedder, get_reranker
from app.retrieval.funnel import apply_funnel
from app.retrieval.search import hybrid_search
from app.services.params import PipelineParams, get_params

router = APIRouter(tags=["search"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    # Leave out one version, as the scan does for the version that holds the source clause.
    exclude_version_id: uuid.UUID | None = None


class HitOut(BaseModel):
    chunk_id: str
    version_id: str
    title: str
    version_label: str
    heading_path: str | None
    page: int | None
    text: str
    score: float  # the RRF score
    vector_rank: int | None  # place in the search by meaning, empty if it was not in the top 25
    keyword_rank: int | None  # place in the search by words, empty if it was not in the top 25
    rerank_score: float  # 0 to 1, how closely the hit addresses the same rule as the query
    kept: bool  # true for the few hits that would go on to the judge


def _out(hits: list[dict]) -> list[HitOut]:
    return [
        HitOut(
            chunk_id=str(h["chunk"].id),
            version_id=str(h["chunk"].version_id),
            title=h["title"],
            version_label=h["version_label"],
            heading_path=h["chunk"].heading_path,
            page=h["chunk"].page,
            text=h["chunk"].text,
            score=h["score"],
            vector_rank=h["vector_rank"],
            keyword_rank=h["keyword_rank"],
            rerank_score=h["rerank_score"],
            kept=h["kept"],
        )
        for h in hits
    ]


def _rerank(source_text: str, hits: list[dict], params: PipelineParams) -> list[dict]:
    try:
        return apply_funnel(source_text, hits, get_reranker(), **params.funnel())
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/search", response_model=list[HitOut])
def search(
    body: SearchIn,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Search the current versions with any text. Embeds the text, so it makes one provider call."""
    try:
        vector = get_embedder().embed([body.query])[0]
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    params = get_params()
    hits = hybrid_search(
        db, user.workspace_id, body.query, vector, body.exclude_version_id, params=params
    )
    return _out(_rerank(body.query, hits, params))


@router.get("/chunks/{chunk_id}/related", response_model=list[HitOut])
def related(
    chunk_id: uuid.UUID,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """What the scan does for one clause: use it as the query, skip its own version.

    The stored vector is reused, so this costs no provider call.
    """
    chunk = db.scalar(
        select(Chunk).where(Chunk.id == chunk_id, Chunk.workspace_id == user.workspace_id)
    )
    if chunk is None:
        raise HTTPException(status_code=404, detail="Chunk not found")
    if chunk.embedding is None:
        raise HTTPException(status_code=409, detail="This chunk has no vector yet")
    text = embedding_input(chunk.context_header, chunk.text, chunk.summary)
    params = get_params()
    hits = hybrid_search(
        db, user.workspace_id, text, chunk.embedding, chunk.version_id, params=params
    )
    return _out(_rerank(text, hits, params))
