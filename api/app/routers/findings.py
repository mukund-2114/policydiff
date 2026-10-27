"""The review queue: list findings, open one, and record what a reviewer decided."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app import auth
from app.db.session import get_db
from app.models import Chunk, Document, DocumentVersion, Finding, PairJudgment, User

router = APIRouter(tags=["findings"])


class SideOut(BaseModel):
    title: str
    version_label: str
    heading_path: str | None
    page: int | None


class FindingOut(BaseModel):
    id: str
    type: str
    status: str
    confidence: float
    explanation: str
    quote_a: str
    quote_b: str
    owner: str | None
    resolution_note: str | None
    a: SideOut
    b: SideOut
    scores: dict  # how the pair got here: ranks, rerank score, judge confidence


class FindingUpdate(BaseModel):
    """Only the fields that are sent change."""

    status: Literal["open", "confirmed", "dismissed", "resolved"] | None = None
    owner: str | None = None
    resolution_note: str | None = None


def _select(workspace_id: uuid.UUID):
    """One row per finding with both chunks, versions and documents joined in."""
    ca, cb = aliased(Chunk), aliased(Chunk)
    va, vb = aliased(DocumentVersion), aliased(DocumentVersion)
    da, dbb = aliased(Document), aliased(Document)
    q = (
        select(Finding, PairJudgment, ca, cb, va, vb, da, dbb)
        .join(PairJudgment, PairJudgment.id == Finding.judgment_id)
        .join(ca, ca.id == PairJudgment.chunk_a)
        .join(cb, cb.id == PairJudgment.chunk_b)
        .join(va, va.id == ca.version_id)
        .join(vb, vb.id == cb.version_id)
        .join(da, da.id == va.document_id)
        .join(dbb, dbb.id == vb.document_id)
        .where(Finding.workspace_id == workspace_id)
    )
    return q


def _out(row) -> FindingOut:
    f, j, c1, c2, v1, v2, d1, d2 = row
    return FindingOut(
        id=str(f.id),
        type=f.type,
        status=f.status,
        confidence=f.confidence,
        explanation=f.explanation,
        quote_a=f.quote_a,
        quote_b=f.quote_b,
        owner=f.owner,
        resolution_note=f.resolution_note,
        a=SideOut(
            title=d1.title,
            version_label=v1.version_label,
            heading_path=c1.heading_path,
            page=c1.page,
        ),
        b=SideOut(
            title=d2.title,
            version_label=v2.version_label,
            heading_path=c2.heading_path,
            page=c2.page,
        ),
        scores=j.scores,
    )


@router.get("/findings", response_model=list[FindingOut])
def findings(
    status: str | None = None,
    type: str | None = None,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    """Findings, most confident first. `status` and `type` narrow the list."""
    q = _select(user.workspace_id)
    if status:
        q = q.where(Finding.status == status)
    if type:
        q = q.where(Finding.type == type)
    return [_out(r) for r in db.execute(q.order_by(Finding.confidence.desc())).all()]


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: uuid.UUID,
    body: FindingUpdate,
    user: User = Depends(auth.require_role("admin", "reviewer")),
    db: Session = Depends(get_db),
):
    """Confirm, dismiss, resolve or reopen a finding, and record who did it."""
    row = db.execute(_select(user.workspace_id).where(Finding.id == finding_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    f = row[0]
    changes = body.model_dump(exclude_unset=True)
    for name, value in changes.items():
        setattr(f, name, value)
    auth.audit(db, user, user.workspace_id, "finding_update", finding_id=str(f.id), **changes)
    db.commit()
    return _out(row)
