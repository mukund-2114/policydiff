"""Chat over the policies: POST /ask/stream sends the answer as it is written."""

import json
import logging
from collections.abc import Iterator
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import auth
from app.db.session import get_engine
from app.models import User
from app.providers.base import ProviderError
from app.providers.registry import get_chat, get_embedder, get_reranker
from app.services.ask import ask_stream

router = APIRouter(tags=["ask"])
log = logging.getLogger(__name__)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[Turn] = Field(default=[], max_length=20)  # the conversation so far
    as_of: date | None = None  # search the versions in effect on this day instead of today's


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/ask/stream")
def ask_question(body: AskIn, user: User = Depends(auth.current_user)):
    """Events: passages, then token pieces, then done (or error).

    The generator opens its own database session, because the request's session is closed before
    a streamed response finishes.
    """
    workspace_id, question = user.workspace_id, body.question.strip()
    history = [t.model_dump() for t in body.history]

    def events() -> Iterator[str]:
        tokens = 0
        with Session(get_engine()) as db:
            try:
                for event in ask_stream(
                    db,
                    workspace_id,
                    question,
                    history,
                    body.as_of,
                    get_chat(fast=True),
                    get_embedder(),
                    get_reranker(),
                ):
                    tokens = event.get("tokens", tokens)
                    yield _sse(event)
            except ProviderError as e:
                yield _sse({"type": "error", "message": str(e)})
                return
            except Exception:  # noqa: BLE001 - tell the page, keep the details in the log
                log.exception("chat failed")
                yield _sse({"type": "error", "message": "Something went wrong. Try again."})
                return
            # The audit log keeps that a question was asked, not what it said.
            auth.audit(
                db,
                user,
                workspace_id,
                "ask",
                as_of=str(body.as_of) if body.as_of else None,
                tokens=tokens,
            )
            db.commit()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
