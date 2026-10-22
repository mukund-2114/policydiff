"""Step 1 of the pipeline: accept an uploaded PDF, store it, register it, and queue the first job.

This is the only place that creates a document version. The upload form and the sample loader
both call register_upload(), so the sample documents go through exactly the same path as yours.
"""

import hashlib
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import audit
from app.config import get_settings
from app.jobs import enqueue_parse
from app.models import Collection, Document, DocumentVersion, User
from app.storage import originals_path

log = logging.getLogger(__name__)


class UploadError(ValueError):
    """A problem the user can fix. The message is shown in the UI."""


def register_upload(
    db: Session,
    user: User,
    *,
    data: bytes,
    title: str,
    collection: str,
    version_label: str,
    effective_from: date | None = None,
    owner_team: str | None = None,
) -> tuple[DocumentVersion, bool]:
    """Returns (version, created). created is False when the same file was uploaded before."""
    if not data.startswith(b"%PDF"):
        raise UploadError("The file is not a PDF.")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise UploadError(f"The file is larger than {get_settings().max_upload_mb} MB.")
    title, collection, version_label = title.strip(), collection.strip(), version_label.strip()
    if not title or not collection or not version_label:
        raise UploadError("Title, collection and version label are required.")
    # These are the column sizes in the database. Checking here gives a clear message instead of a 500.
    if len(title) > 300 or len(collection) > 200 or len(version_label) > 50 or len(owner_team or "") > 200:
        raise UploadError("Title (300), collection (200), version label (50) or owner team (200) is too long.")

    # Same bytes, same file: skip it instead of storing and processing a copy.
    sha = hashlib.sha256(data).hexdigest()
    ws = user.workspace_id
    existing = db.scalar(
        select(DocumentVersion).where(DocumentVersion.workspace_id == ws, DocumentVersion.sha256 == sha)
    )
    if existing:
        if existing.status == "failed" and existing.failed_stage == "queued":
            _queue(db, existing)  # saved earlier but never queued: try again instead of skipping
            return existing, True
        return existing, False

    coll = db.scalar(select(Collection).where(Collection.workspace_id == ws, Collection.name == collection))
    if coll is None:
        coll = Collection(workspace_id=ws, name=collection)
        db.add(coll)
        db.flush()
    doc = db.scalar(select(Document).where(Document.collection_id == coll.id, Document.title == title))
    if doc is None:
        doc = Document(workspace_id=ws, collection_id=coll.id, title=title, owner_team=owner_team or None)
        db.add(doc)
        db.flush()
    clash = db.scalar(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version_label == version_label
        )
    )
    if clash:
        raise UploadError(f"{title} already has a version labelled {version_label}.")

    version = DocumentVersion(
        workspace_id=ws,
        document_id=doc.id,
        version_label=version_label,
        effective_from=effective_from,
        status="queued",
        sha256=sha,
    )
    db.add(version)
    db.flush()  # gives the version its id, which names the file on disk
    path = originals_path(version.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    version.file_path = str(path)
    audit(db, user, ws, "document_upload", version_id=str(version.id), title=title, sha256=sha)
    db.commit()  # the version must be saved before the job is queued, or the worker may not find it

    _queue(db, version)
    return version, True


def _queue(db: Session, version: DocumentVersion) -> None:
    version.status, version.failed_stage = "queued", None
    db.commit()
    try:
        enqueue_parse(version.id)
    except Exception as exc:  # noqa: BLE001
        log.exception("could not queue parse job for %s", version.id)
        version.status = "failed"
        version.failed_stage = "queued"
        db.commit()
        raise UploadError(f"Saved the file but could not queue processing: {exc}") from exc
