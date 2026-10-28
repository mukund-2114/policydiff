"""Jobs the worker runs. One job per pipeline stage, so a failed stage can be retried alone."""

import json
import logging
import tempfile
import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

import pymupdf
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import audit
from app.config import get_settings
from app.db.session import get_engine
from app.jobs import enqueue_chunk, enqueue_embed, enqueue_enrich, queue
from app.models import Chunk, Document, DocumentVersion, Finding, PairJudgment, Scan
from app.pipeline import enrich
from app.pipeline.chunk import FIGURE_PLACEHOLDER, chunk_pages, context_header
from app.pipeline.embed import MAX_CHARS, embedding_input
from app.pipeline.judge import PROMPT_VERSION
from app.pipeline.parse import parse_pdf
from app.pipeline.stages import run_stage
from app.providers.base import ProviderError
from app.providers.registry import (
    effective_config,
    get_chat,
    get_embedder,
    get_reranker,
    get_vision,
)
from app.retrieval.funnel import MAX_RERANKED, MMR_KEEP, MMR_LAMBDA, RELATED_THRESHOLD
from app.services.scan import finish, run_scan
from app.services.versions import plan_supersede
from app.storage import get_storage, parsed_key

log = logging.getLogger(__name__)


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
                raw,
                settings.chunk_max_tokens,
                settings.chunk_overlap_tokens,
                figures=settings.summarize_media,
            )
            # Judgments and findings point at the old chunks, so they go with them. A new scan
            # judges the new chunks.
            old_ids = select(Chunk.id).where(Chunk.version_id == version.id)
            stale = select(PairJudgment.id).where(
                PairJudgment.chunk_a.in_(old_ids) | PairJudgment.chunk_b.in_(old_ids)
            )
            db.execute(delete(Finding).where(Finding.judgment_id.in_(stale)))
            db.execute(delete(PairJudgment).where(PairJudgment.id.in_(stale)))
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
            enqueue_enrich(version.id)


@queue.task(name="enrich_version")
def enrich_version(version_id: str) -> None:
    """Describe tables and figures and pull facts out of chunks, then hand over to embedding.

    Safe to run again: it fills only what is still empty. A chunk the model fails on is left empty
    and logged in the stage detail, so one bad answer does not stop the document.
    """
    settings = get_settings()
    with Session(get_engine()) as db:
        version = db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None:
            return
        with run_stage(db, version, "enriching", "chunking") as stage:
            chunks = db.scalars(
                select(Chunk).where(Chunk.version_id == version.id).order_by(Chunk.position)
            ).all()
            detail = {"summaries": 0, "figures": 0, "facts": 0, "failed": 0, "tokens": 0}
            if (settings.summarize_media or settings.extract_facts) and chunks:
                chat, vision = get_chat(), get_vision()
                with tempfile.TemporaryDirectory() as tmp:
                    pdf = Path(tmp) / "doc.pdf"
                    get_storage().download(version.file_path, pdf)
                    with pymupdf.open(pdf) as doc:
                        for c in chunks:
                            _enrich_chunk(c, chat, vision, doc, settings, detail)
                            db.commit()
            stage.detail = detail
        if version.status != "failed":
            version.status = "chunked"
            db.commit()
            enqueue_embed(version.id)


def _enrich_chunk(c: Chunk, chat, vision, pdf, settings, detail: dict) -> None:
    try:
        if settings.summarize_media and c.kind == "table" and not c.summary:
            c.summary, tokens = enrich.summarize_table(chat, c.heading_path, c.text)
            detail["summaries"] += 1
            detail["tokens"] += tokens
        elif settings.summarize_media and c.kind == "figure" and c.text == FIGURE_PLACEHOLDER:
            box = c.bbox["boxes"][0]
            page = pdf[box["page"] - 1]
            png = page.get_pixmap(clip=pymupdf.Rect(*box["bbox"]), dpi=200).tobytes("png")
            reading, tokens = enrich.read_figure(vision, c.heading_path, png)
            c.text = enrich.figure_text(reading)
            detail["figures"] += 1
            detail["tokens"] += tokens
        # A figure's text already lists its labelled values, so it gets no separate facts.
        if settings.extract_facts and c.facts is None and c.kind != "figure":
            c.facts, tokens = _facts(chat, c)
            detail["facts"] += 1
            detail["tokens"] += tokens
    except ProviderError as e:
        detail["failed"] += 1
        log.warning("enrich failed for chunk %s: %s", c.id, e)


def _facts(chat, c: Chunk) -> tuple[dict, int]:
    facts, tokens = enrich.extract_facts(chat, c.heading_path, c.text)
    return {"items": facts}, tokens


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


@queue.task(name="scan_version")
def scan_version(scan_id: str) -> None:
    """Look for conflicts between every clause of one version and the rest of the library."""
    with Session(get_engine()) as db:
        scan = db.get(Scan, uuid.UUID(scan_id))
        if scan is None or scan.status != "queued":
            return
        version = db.get(DocumentVersion, uuid.UUID(scan.scope.removeprefix("version:")))
        scan.status, scan.started_at = "running", datetime.now(UTC)
        db.commit()
        cfg = effective_config()
        snapshot = {  # what this scan ran with, so a finding can be traced to it
            "chat": f"{cfg.chat.provider}/{cfg.chat.model}",
            "rerank": f"{cfg.rerank.provider}/{cfg.rerank.model or 'default'}",
            "threshold": RELATED_THRESHOLD,
            "max_reranked": MAX_RERANKED,
            "mmr_lambda": MMR_LAMBDA,
            "mmr_keep": MMR_KEEP,
            "prompt_version": PROMPT_VERSION,
        }
        try:
            stats = run_scan(db, scan, version, get_chat(), get_reranker())
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.exception("scan %s failed", scan_id)
            finish(scan, "failed", {**snapshot, "error": f"{type(exc).__name__}: {exc}"[:500]})
        else:
            # A scan where the judge never answered is a failure, not an empty result.
            ok = stats.failed == 0 or stats.judged > 0
            finish(scan, "done" if ok else "failed", {**snapshot, "stats": asdict(stats)})
        audit(
            db,
            None,
            scan.workspace_id,
            "scan_finish",
            scan_id=str(scan.id),
            status=scan.status,
            model=snapshot["chat"],
            judge_calls=scan.judge_calls,
            tokens=scan.tokens,
        )
        db.commit()
