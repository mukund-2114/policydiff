"""Records each pipeline stage in the database so the UI can show what happened and its timing.

Usage in a job:

    with run_stage(db, version, "parsing", "parsing") as stage:
        ...do the work...
        stage.detail = {"pages": 12}      # shown in the UI

If the work raises, the stage and the version are marked failed, with the error text. The error is
logged and swallowed, so the job itself finishes and is not retried into duplicate rows.
"""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import DocumentVersion, VersionStage

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@contextmanager
def run_stage(db: Session, version: DocumentVersion, stage: str, version_status: str):
    row = VersionStage(workspace_id=version.workspace_id, version_id=version.id, stage=stage)
    version.status = version_status
    version.failed_stage = None
    db.add(row)
    db.commit()  # commit now, so the UI sees "running" while the work is going on
    try:
        yield row
        row.status = "done"
        row.finished_at = _now()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.exception("stage %s failed for version %s", stage, version.id)
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:500]
        row.finished_at = _now()
        version.status = "failed"
        version.failed_stage = stage
        db.commit()
