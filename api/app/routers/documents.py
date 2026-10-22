"""Upload, list and inspect documents. Everything the Documents pages in the web app call."""

import json
import uuid
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db.session import get_db
from app.models import Collection, Document, DocumentVersion, User, VersionStage
from app.pipeline.parse import simplify
from app.services.ingest import UploadError, register_upload

router = APIRouter(tags=["documents"])


class VersionOut(BaseModel):
    id: str
    document_id: str
    title: str
    collection: str
    owner_team: str | None
    version_label: str
    effective_from: date | None
    status: str
    failed_stage: str | None
    created_at: datetime
    pages: int | None


class StageOut(BaseModel):
    stage: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    detail: dict | None
    error: str | None


class VersionDetail(VersionOut):
    stages: list[StageOut]


class UploadOut(BaseModel):
    version: VersionOut
    duplicate: bool  # true when the same file was already uploaded


def _rows(db: Session, user: User, version_id: uuid.UUID | None = None):
    q = (
        select(DocumentVersion, Document, Collection)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(Collection, Collection.id == Document.collection_id)
        .where(DocumentVersion.workspace_id == user.workspace_id)
        .order_by(Document.title, DocumentVersion.created_at)
    )
    if version_id:
        q = q.where(DocumentVersion.id == version_id)
    return db.execute(q).all()


def _pages(db: Session, version_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    rows = db.execute(
        select(VersionStage.version_id, VersionStage.detail).where(
            VersionStage.version_id.in_(version_ids),
            VersionStage.stage == "parsing",
            VersionStage.status == "done",
        )
    ).all()
    return {vid: detail["pages"] for vid, detail in rows if detail}


def _version_out(v: DocumentVersion, d: Document, c: Collection, pages: dict) -> dict:
    return dict(
        id=str(v.id),
        document_id=str(d.id),
        title=d.title,
        collection=c.name,
        owner_team=d.owner_team,
        version_label=v.version_label,
        effective_from=v.effective_from,
        status=v.status,
        failed_stage=v.failed_stage,
        created_at=v.created_at,
        pages=pages.get(v.id),
    )


def _get_version(db: Session, user: User, version_id: uuid.UUID):
    rows = _rows(db, user, version_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Version not found")
    return rows[0]


@router.post("/documents/upload", response_model=UploadOut)
def upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    collection: str = Form("General"),
    version_label: str = Form("1.0"),
    effective_from: date | None = Form(None),
    owner_team: str | None = Form(None),
    user: User = Depends(auth.require_role("admin", "reviewer")),
    db: Session = Depends(get_db),
):
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)  # read one byte past the limit so register_upload can reject it
    try:
        version, created = register_upload(
            db,
            user,
            data=data,
            title=title,
            collection=collection,
            version_label=version_label,
            effective_from=effective_from,
            owner_team=owner_team,
        )
    except UploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    v, d, c = _get_version(db, user, version.id)
    return UploadOut(version=_version_out(v, d, c, _pages(db, [v.id])), duplicate=not created)


@router.get("/documents", response_model=list[VersionOut])
def list_documents(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    rows = _rows(db, user)
    pages = _pages(db, [v.id for v, _, _ in rows])
    return [_version_out(v, d, c, pages) for v, d, c in rows]


@router.get("/versions/{version_id}", response_model=VersionDetail)
def version_detail(version_id: uuid.UUID, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    v, d, c = _get_version(db, user, version_id)
    stages = db.scalars(
        select(VersionStage).where(VersionStage.version_id == v.id).order_by(VersionStage.started_at)
    ).all()
    return VersionDetail(
        **_version_out(v, d, c, _pages(db, [v.id])),
        stages=[
            StageOut(
                stage=s.stage,
                status=s.status,
                started_at=s.started_at,
                finished_at=s.finished_at,
                duration_ms=int((s.finished_at - s.started_at).total_seconds() * 1000) if s.finished_at else None,
                detail=s.detail,
                error=s.error,
            )
            for s in stages
        ],
    )


@router.get("/versions/{version_id}/file")
def version_file(version_id: uuid.UUID, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """The original PDF, shown inline in the browser. Only served to a signed-in user."""
    v, d, _ = _get_version(db, user, version_id)
    if not v.file_path or not Path(v.file_path).exists():
        raise HTTPException(status_code=404, detail="File is missing")
    return FileResponse(
        v.file_path, media_type="application/pdf", filename=f"{d.title}.pdf", content_disposition_type="inline"
    )


@router.get("/versions/{version_id}/parsed")
def version_parsed(version_id: uuid.UUID, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """What the parser saw, page by page: text blocks with font size, detected tables, image count."""
    v, _, _ = _get_version(db, user, version_id)
    if not v.parsed_json_path or not Path(v.parsed_json_path).exists():
        raise HTTPException(status_code=404, detail="This version has not been parsed yet")
    raw = json.loads(Path(v.parsed_json_path).read_text(encoding="utf-8"))
    return {"pages": simplify(raw)}
