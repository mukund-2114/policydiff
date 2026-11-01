"""The audit log: who did what and when, as a list and as a CSV download. Admin only.

Events are written by `auth.audit` next to the action they record (sign in, upload, scan, decision,
settings change, question asked). Details hold names, ids and counts, never keys or document text.
"""

import csv
import io
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db.session import get_db
from app.models import AuditEvent, User

router = APIRouter(tags=["audit"])

CSV_LIMIT = 50_000


class AuditOut(BaseModel):
    id: str
    at: str
    user: str | None
    action: str
    target: str | None
    detail: dict | None


def _query(workspace_id: uuid.UUID, action: str | None):
    q = (
        select(AuditEvent, User.email)
        .outerjoin(User, User.id == AuditEvent.user_id)
        .where(AuditEvent.workspace_id == workspace_id)
    )
    if action:
        q = q.where(AuditEvent.action == action)
    return q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())


def _out(e: AuditEvent, email: str | None) -> AuditOut:
    return AuditOut(
        id=str(e.id),
        at=e.created_at.isoformat(),
        user=email,
        action=e.action,
        target=e.target,
        detail=e.detail,
    )


@router.get("/audit", response_model=list[AuditOut])
def audit_log(
    action: str | None = None,
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    """Newest first. `limit` is capped at 500."""
    q = _query(user.workspace_id, action).limit(min(max(limit, 1), 500)).offset(max(offset, 0))
    return [_out(e, email) for e, email in db.execute(q).all()]


def safe_cell(value) -> str:
    """Stop a spreadsheet from running a cell as a formula (CSV injection).

    A cell that starts with = + - @ or a control character is read as a formula by Excel and
    Sheets, so a quote taken from a document could run something. A leading apostrophe makes
    it text.
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_response(filename: str, header: list[str], rows) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(c) for c in row])
    return Response(
        # The byte order mark lets Excel open UTF-8 text without garbling it.
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit.csv")
def audit_csv(
    action: str | None = None,
    user: User = Depends(auth.require_role("admin")),
    db: Session = Depends(get_db),
):
    rows = db.execute(_query(user.workspace_id, action).limit(CSV_LIMIT)).all()
    return csv_response(
        "audit-log.csv",
        ["time", "user", "action", "target", "detail"],
        ([e.created_at.isoformat(), email, e.action, e.target, e.detail] for e, email in rows),
    )
