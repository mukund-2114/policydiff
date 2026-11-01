"""Start a conflict scan of one version and follow how it is going."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db.session import get_db
from app.jobs import enqueue_scan
from app.models import DocumentVersion, Scan, User

router = APIRouter(tags=["scans"])

ACTIVE = ("queued", "running")


class ScanOut(BaseModel):
    id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    judge_calls: int
    tokens: int
    stats: dict | None  # counts: clauses, candidates, cached, judged, findings, unverified, failed
    progress: dict | None  # while running: which clause of how many
    error: str | None
    settings: dict  # the models and numbers this scan ran with


def _scan_out(s: Scan) -> ScanOut:
    snap = dict(s.settings_snapshot or {})
    return ScanOut(
        id=str(s.id),
        status=s.status,
        started_at=s.started_at,
        finished_at=s.finished_at,
        judge_calls=s.judge_calls,
        tokens=s.tokens,
        stats=snap.pop("stats", None),
        progress=snap.pop("progress", None),
        error=snap.pop("error", None),
        settings=snap,
    )


def _own_version(db: Session, user: User, version_id: uuid.UUID) -> DocumentVersion:
    v = db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id, DocumentVersion.workspace_id == user.workspace_id
        )
    )
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return v


@router.post("/versions/{version_id}/scan", response_model=ScanOut, status_code=202)
def start_scan(
    version_id: uuid.UUID,
    user: User = Depends(auth.require_role("admin", "reviewer")),
    db: Session = Depends(get_db),
):
    """Compare every clause of this version with the other current versions."""
    v = _own_version(db, user, version_id)
    if v.status != "ready":
        raise HTTPException(status_code=409, detail="Wait until the document is ready.")
    scope = f"version:{v.id}"
    busy = db.scalar(select(Scan.id).where(Scan.scope == scope, Scan.status.in_(ACTIVE)))
    if busy:
        raise HTTPException(status_code=409, detail="A scan of this version is already running.")
    scan = Scan(workspace_id=user.workspace_id, scope=scope, status="queued")
    db.add(scan)
    auth.audit(db, user, user.workspace_id, "scan_start", version_id=str(v.id))
    db.commit()
    try:
        enqueue_scan(scan.id)
    except Exception:  # noqa: BLE001 - a scan that was never queued must not block the next try
        scan.status = "failed"
        scan.settings_snapshot = {"error": "Could not queue the scan."}
        db.commit()
        raise HTTPException(status_code=503, detail="Could not queue the scan.") from None
    return _scan_out(scan)


@router.get("/versions/{version_id}/scans", response_model=list[ScanOut])
def version_scans(
    version_id: uuid.UUID,
    user: User = Depends(auth.current_user),
    db: Session = Depends(get_db),
):
    v = _own_version(db, user, version_id)
    rows = db.scalars(
        select(Scan)
        .where(Scan.scope == f"version:{v.id}")
        .order_by(Scan.started_at.desc().nulls_first())
        .limit(5)
    )
    return [_scan_out(s) for s in rows]
