"""The conflict scan: every clause of one version, against everything else that is current.

For each clause it runs the funnel (search, rerank, MMR), skips pairs already judged, asks the
judge about the rest, checks the quotes, and stores the result. Each pair is saved as soon as it is
judged, so a scan that stops half way keeps its work, and running it again skips what is done
(the pair cache).
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentVersion, Finding, PairJudgment, Scan
from app.pipeline.embed import embedding_input
from app.pipeline.judge import (
    PROMPT_VERSION,
    Clause,
    final_confidence,
    judge_pair,
    numbers_differ,
    quotes_verified,
)
from app.providers.base import ChatModel, ProviderError, Reranker
from app.retrieval import funnel
from app.retrieval.search import hybrid_search

log = logging.getLogger(__name__)


@dataclass
class ScanStats:
    clauses: int = 0
    candidates: int = 0  # pairs that came out of the funnel
    cached: int = 0  # skipped: the same pair was judged before
    judged: int = 0
    findings: int = 0
    unverified: int = 0  # the judge reported a conflict but a quote was not in the text
    failed: int = 0  # the judge gave no usable answer twice
    tokens: int = 0
    errors: list[str] = field(default_factory=list)


def _clause(db: Session, chunk: Chunk) -> Clause:
    v, d = db.execute(
        select(DocumentVersion, Document)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentVersion.id == chunk.version_id)
    ).one()
    return Clause(d.title, v.version_label, v.effective_from, chunk.heading_path, chunk.text)


def _judge_one(db, scan, source: Chunk, hit: dict, chat: ChatModel, stats: ScanStats) -> None:
    cand: Chunk = hit["chunk"]
    out, tokens = judge_pair(chat, _clause(db, source), _clause(db, cand))
    stats.judged += 1
    stats.tokens += tokens
    verdict = out.verdict
    verified = verdict == "no_conflict" or quotes_verified(out, source.text, cand.text)
    differ = numbers_differ(out.quote_a, out.quote_b)
    confidence = final_confidence(out.confidence, hit["rerank_score"], differ)
    judgment = PairJudgment(
        workspace_id=scan.workspace_id,
        pair_key=funnel.pair_key(source.id, cand.id),
        chunk_a=source.id,
        chunk_b=cand.id,
        scan_id=scan.id,
        verdict=verdict if verified else "unverified",
        scores={
            "rrf": hit["score"],
            "vector_rank": hit["vector_rank"],
            "keyword_rank": hit["keyword_rank"],
            "rerank": hit["rerank_score"],
            "judge_confidence": out.confidence,
            "numbers_differ": differ,
            "quotes_verified": verified,
            "confidence": confidence,
            "prompt_version": PROMPT_VERSION,
        },
        raw_output=out.model_dump(),
    )
    db.add(judgment)
    db.flush()  # the finding needs the judgment's id
    if verdict == "no_conflict":
        return
    if not verified:  # guide step 9: a quote that is not in the text means the finding is dropped
        stats.unverified += 1
        return
    db.add(
        Finding(
            workspace_id=scan.workspace_id,
            judgment_id=judgment.id,
            type=out.type,
            quote_a=out.quote_a,
            quote_b=out.quote_b,
            explanation=out.explanation,
            confidence=confidence,
            owner=out.suggested_owner,
        )
    )
    stats.findings += 1


def run_scan(
    db: Session, scan: Scan, version: DocumentVersion, chat: ChatModel, reranker: Reranker
) -> ScanStats:
    stats = ScanStats()
    done_pairs = set(
        db.scalars(
            select(PairJudgment.pair_key).where(PairJudgment.workspace_id == scan.workspace_id)
        )
    )
    chunks = db.scalars(
        select(Chunk)
        .where(Chunk.version_id == version.id, Chunk.embedding.is_not(None))
        .order_by(Chunk.position)
    ).all()
    for chunk in chunks:
        stats.clauses += 1
        text = embedding_input(chunk.context_header, chunk.text, chunk.summary)
        hits = hybrid_search(db, scan.workspace_id, text, chunk.embedding, version.id)
        for hit in funnel.apply_funnel(text, hits, reranker):
            if not hit["kept"]:
                continue
            stats.candidates += 1
            key = funnel.pair_key(chunk.id, hit["chunk"].id)
            if key in done_pairs:
                stats.cached += 1
                continue
            done_pairs.add(key)
            try:
                _judge_one(db, scan, chunk, hit, chat, stats)
            except ProviderError as e:  # one bad pair must not stop the scan
                stats.failed += 1
                stats.errors.append(str(e)[:200])
                done_pairs.discard(key)
                log.warning("judge failed for pair %s: %s", key, e)
            scan.judge_calls, scan.tokens = stats.judged, stats.tokens
            db.commit()
    return stats


def finish(scan: Scan, status: str, snapshot: dict) -> None:
    scan.status = status
    scan.finished_at = datetime.now(UTC)
    scan.settings_snapshot = snapshot
