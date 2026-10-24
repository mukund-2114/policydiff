"""Jobs the worker runs. One job per pipeline stage, so a failed stage can be retried alone."""

import json
import tempfile
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_engine
from app.jobs import enqueue_chunk, enqueue_embed, queue
from app.models import Chunk, Document, DocumentVersion
from app.pipeline.chunk import chunk_pages, context_header
from app.pipeline.embed import MAX_CHARS, embedding_input
from app.pipeline.parse import parse_pdf
from app.pipeline.stages import run_stage
from app.providers.registry import get_embedder
from app.services.versions import plan_supersede
from app.storage import get_storage, parsed_key


@queue.task(name="parse_version")
def parse_version(version_id: str) -> None:
    with Session(get_engine()) as db:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None:
            return
        with run_stage(db, version, "parsing", "parsing") as stage:
            storage = get_storage()
            # The parser needs a real file, so copy the PDF to a temp folder that is removed after.
            with tempfile.TemporaryDirectory() as tmp:
                pdf = Path(tmp) / "doc.pdf"
                storage.download(version.file_path, pdf)
                raw, summary = parse_pdf(pdf)
            key = parsed_key(version.id)
            storage.put(key, json.dumps(raw).encode("utf-8"))
            version.parsed_json_path = key
            stage.detail = summary
        if version.status != "failed":
            version.status = "parsed"
            db.commit()
            enqueue_chunk(version.id)


@queue.task(name="chunk_version")
def chunk_version(version_id: str) -> None:
    """Cut the saved parser output into clauses, then add the context line to each one.

    Running it again replaces the old chunks, so it is also how a version is re-chunked.
    """
    settings = get_settings()
    with Session(get_engine()) as db:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None or not version.parsed_json_path:
            return
        with run_stage(db, version, "chunking", "chunking") as stage:
            raw = json.loads(get_storage().get(version.parsed_json_path))
            drafts, stats = chunk_pages(
                raw, settings.chunk_max_tokens, settings.chunk_overlap_tokens
            )
            db.execute(delete(Chunk).where(Chunk.version_id == version.id))
            for i, d in enumerate(drafts):
                db.add(
                    Chunk(
                        workspace_id=version.workspace_id,
                        version_id=version.id,
                        kind=d.kind,
                        position=i,
                        heading_path=d.heading_path,
                        text=d.text,
                        page=d.page,
                        bbox={"boxes": d.boxes},
                    )
                )
            stage.detail = stats
        if version.status == "failed":
            return
        with run_stage(db, version, "headers", "chunking") as stage:
            doc = db.get(Document, version.document_id)
            chunks = db.scalars(select(Chunk).where(Chunk.version_id == version.id)).all()
            for c in chunks:
                c.context_header = context_header(
                    doc.title, version.version_label, version.effective_from, c.heading_path
                )
            stage.detail = {
                "chunks": len(chunks),
                "example": chunks[0].context_header if chunks else "",
            }
        if version.status != "failed":
            version.status = "chunked"
            db.commit()
            enqueue_embed(version.id)


@queue.task(name="embed_version")
def embed_version(version_id: str) -> None:
    """Turn each chunk into a vector and a keyword index. Safe to run again."""
    with Session(get_engine()) as db:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None:
            return
        with run_stage(db, version, "embedding", "embedding") as stage:
            chunks = db.scalars(
                select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.position)
            ).all()
            inputs = [embedding_input(c.context_header, c.text, c.summary) for c in chunks]
            embedder = get_embedder()
            for chunk, vector in zip(chunks, embedder.embed(inputs), strict=True):
                chunk.embedding = vector
                chunk.embedding_model = embedder.model
            # The keyword index is built by Postgres from the same text the embedding saw.
            db.execute(
                update(Chunk)
                .where(Chunk.version_id == version.id)
                .values(
                    tsv=func.to_tsvector(
                        "english", func.concat_ws(" ", Chunk.context_header, Chunk.text)
                    )
                )
            )
            stage.detail = {
                "chunks": len(chunks),
                "model": embedder.model,
                "dimensions": embedder.dims,
                "cut_to_fit": sum(len(x) >= MAX_CHARS for x in inputs),
            }
        if version.status != "failed":
            version.status = "ready"
            others = db.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == version.document_id,
                    DocumentVersion.id != version.id,
                )
            ).all()
            for old, end in plan_supersede(version, list(others), date.today()):
                old.status, old.effective_to = "superseded", end
            db.commit()
