"""The ten tables from the architecture guide. Every row carries workspace_id."""

import uuid
from datetime import date, datetime

import uuid_utils
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings


def new_id() -> uuid.UUID:
    """UUIDv7: time-ordered, good for indexes."""
    return uuid.UUID(str(uuid_utils.uuid7()))


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=new_id)


def _ws() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspace.id"), index=True)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspace"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "user"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin, reviewer, viewer


class Collection(Base):
    __tablename__ = "collection"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)


class Document(Base):
    __tablename__ = "document"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    owner_team: Mapped[str | None] = mapped_column(String(200))


class DocumentVersion(Base):
    __tablename__ = "document_version"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    # queued, parsing, parsed, summarizing, chunking, embedding, ready, failed, superseded
    status: Mapped[str] = mapped_column(String(20), default="queued")
    failed_stage: Mapped[str | None] = mapped_column(String(20))
    file_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    parsed_json_path: Mapped[str | None] = mapped_column(
        Text
    )  # raw parser output, saved so we can re-chunk without re-parsing
    created_at: Mapped[datetime] = _now()


class VersionStage(Base):
    """One row per pipeline stage run on a document version. The UI draws the pipeline from it."""

    __tablename__ = "version_stage"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_version.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20))  # parsing, chunking, embedding, ...
    status: Mapped[str] = mapped_column(String(10), default="running")  # running, done, failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict | None] = mapped_column(JSONB)  # counts shown in the UI, e.g. pages
    error: Mapped[str | None] = mapped_column(Text)


class Chunk(Base):
    __tablename__ = "chunk"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_version.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="text")  # text, table, figure
    heading_path: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    context_header: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    original_ref: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    facts: Mapped[dict | None] = mapped_column(JSONB)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding = mapped_column(Vector(get_settings().embed_dims), nullable=True)
    tsv = mapped_column(TSVECTOR, nullable=True)
    __table_args__ = (
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
    )


class Scan(Base):
    __tablename__ = "scan"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    scope: Mapped[str] = mapped_column(String(100))
    settings_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    judge_calls: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)


class PairJudgment(Base):
    __tablename__ = "pair_judgment"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    pair_key: Mapped[str] = mapped_column(String(100), index=True)
    chunk_a: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunk.id"))
    chunk_b: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunk.id"))
    scan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scan.id"), index=True)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    verdict: Mapped[str] = mapped_column(String(20))
    raw_output: Mapped[dict | None] = mapped_column(JSONB)


class Finding(Base):
    __tablename__ = "finding"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    judgment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pair_judgment.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    quote_a: Mapped[str] = mapped_column(Text)
    quote_b: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open, confirmed, dismissed, resolved
    owner: Mapped[str | None] = mapped_column(String(200))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class AuditEvent(Base):
    """Append only. Nothing in the app updates or deletes these rows."""

    __tablename__ = "audit_event"
    id: Mapped[uuid.UUID] = _pk()
    workspace_id: Mapped[uuid.UUID] = _ws()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    action: Mapped[str] = mapped_column(String(60), index=True)
    target: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
