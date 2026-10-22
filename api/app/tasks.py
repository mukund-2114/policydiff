"""Jobs the worker runs. One job per pipeline stage, so a failed stage can be retried alone."""

import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.jobs import queue
from app.models import DocumentVersion
from app.pipeline.parse import parse_pdf
from app.pipeline.stages import run_stage
from app.storage import parsed_path


@queue.task(name="parse_version")
def parse_version(version_id: str) -> None:
    with Session(get_engine()) as db:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None:
            return
        with run_stage(db, version, "parsing", "parsing") as stage:
            raw, summary = parse_pdf(Path(version.file_path))
            out = parsed_path(version.id)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(raw), encoding="utf-8")
            version.parsed_json_path = str(out)
            stage.detail = summary
        if version.status != "failed":
            version.status = "parsed"  # chunking, embedding and the rest arrive in later sessions
            db.commit()
