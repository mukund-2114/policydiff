"""Q&A with an optional as-of date: POST /ask."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app.db.session import get_db
from app.models import User
from app.providers.base import ProviderError
from app.providers.registry import get_chat, get_embedder, get_reranker
from app.services.ask import ask

router = APIRouter(tags=["ask"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    as_of: date | None = None  # search the versions in effect on this day instead of today's


class PassageOut(BaseModel):
    n: int
    chunk_id: str
    version_id: str
    title: str
    version_label: str
    heading_path: str | None
    page: int | None
    kind: str
    text: str
    cited: bool


class FindingRef(BaseModel):
    id: str
    type: str
    status: str
    confidence: float
    explanation: str
    between: str


class AskOut(BaseModel):
    answer: str
    passages: list[PassageOut]
    findings: list[FindingRef]
    tokens: int


@router.post("/ask", response_model=AskOut)
def ask_question(
    body: AskIn, user: User = Depends(auth.current_user), db: Session = Depends(get_db)
):
    try:
        result = ask(
            db,
            user.workspace_id,
            body.question.strip(),
            body.as_of,
            get_chat(),
            get_embedder(),
            get_reranker(),
        )
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    # The audit log keeps that a question was asked, not what it said.
    auth.audit(db, user, user.workspace_id, "ask", as_of=str(body.as_of) if body.as_of else None)
    db.commit()
    return {
        **result,
        "passages": [
            {**p, "chunk_id": str(p["chunk_id"]), "version_id": str(p["version_id"])}
            for p in result["passages"]
        ],
    }
