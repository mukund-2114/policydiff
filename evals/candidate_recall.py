"""Candidate recall: of the planted conflicts, how many partner clauses does the funnel find?

Run it inside the api container, where the database and the models are:

    docker compose --env-file ../.env exec -T api python - < ../evals/candidate_recall.py

To see what multi-query adds, run it twice and compare the "Found after" lines:
the second time with REWRITES=3 (that many extra wordings per clause, as scan_rewrites does):

    docker compose --env-file ../.env exec -T -e REWRITES=3 api \
        python - < ../evals/candidate_recall.py

For each labelled conflict the two sides are found among the stored chunks. Each side is used as
the query (the scan does this for every clause) and we check whether the other side comes back,
first after search and RRF, then after the reranker and MMR. A conflict counts as found if either
direction finds it, because the scan judges a pair once. Figure sides are not chunked until S11, so
those 2 conflicts are listed but left out of the score.
"""

import json
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import Chunk, Document, DocumentVersion, Workspace
from app.pipeline.embed import embedding_input
from app.providers.registry import get_chat, get_embedder, get_reranker
from app.retrieval.funnel import apply_funnel
from app.retrieval.multi_query import extra_queries
from app.retrieval.search import hybrid_search

LABELS = "/samples/labels.json"
REWRITES = int(os.environ.get("REWRITES", "0"))  # extra wordings per clause, 0 to 5
# Optional settings to try: threshold, how many to keep after MMR, MMR lambda.
KNOBS = dict(zip(("threshold", "keep", "lam"), map(float, sys.argv[1:4]), strict=False))
if "keep" in KNOBS:
    KNOBS["keep"] = int(KNOBS["keep"])


def squash(text):
    """Collapse every run of whitespace, because the PDF wraps a clause across lines."""
    return " ".join(text.split())


def find_chunk(chunks, side):
    """The chunk of side['doc'] that holds the quoted clause, or the table row's cells."""
    if side["kind"] == "figure":
        return None  # figures are not chunked until S11
    is_table = side["kind"] == "table"
    wanted = (
        [squash(c) for c in side["quote"].split(" | ")] if is_table else [squash(side["quote"])]
    )
    for c in chunks.get(side["doc"], []):
        if (c.kind == "table") == is_table and all(w in squash(c.text) for w in wanted):
            return c
    return None


def main():
    labels = json.load(open(LABELS, encoding="utf-8"))["conflicts"]
    reranker = get_reranker()
    chat, embedder = (get_chat(fast=True), get_embedder()) if REWRITES else (None, None)
    with Session(get_engine()) as db:
        ws = db.scalar(select(Workspace.id))
        rows = db.execute(
            select(Chunk, Document.title)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.status == "ready", Chunk.workspace_id == ws)
        ).all()
        chunks = {}
        for c, title in rows:
            chunks.setdefault(title, []).append(c)

        scored = found_search = found_kept = 0
        kept_counts = []
        for label in labels:
            a, b = (find_chunk(chunks, label[s]) for s in "ab")
            if a is None or b is None:
                why = (
                    "figure not chunked yet"
                    if "figure" in (label["a"]["kind"], label["b"]["kind"])
                    else "side not found"
                )
                print(f"{label['id']} {label['type']:20} SKIP ({why})")
                continue
            scored += 1
            in_search = in_kept = False
            scores = []
            for src, other in ((a, b), (b, a)):
                text = embedding_input(src.context_header, src.text, src.summary)
                extra = extra_queries(chat, embedder, text, REWRITES)[0] if REWRITES else []
                hits = hybrid_search(
                    db, ws, text, src.embedding, src.version_id, extra_queries=extra
                )
                hits = apply_funnel(text, hits, reranker, **KNOBS)
                in_search |= any(h["chunk"].id == other.id for h in hits)
                in_kept |= any(h["chunk"].id == other.id and h["kept"] for h in hits)
                kept_counts.append(sum(h["kept"] for h in hits))
                mine = [h["rerank_score"] for h in hits if h["chunk"].id == other.id]
                scores.append(mine[0] if mine else None)
            found_search += in_search
            found_kept += in_kept
            yes = {True: "yes", False: "NO "}
            line = f"{label['id']} {label['type']:20}"
            shown = " ".join("-" if x is None else f"{x:.2f}" for x in scores)
            print(f"{line} search={yes[in_search]} funnel={yes[in_kept]} scores {shown}")
        print(f"\nScored {scored} conflicts (figure conflicts left out)")
        print(
            f"Average pairs sent to the judge per clause: {sum(kept_counts) / len(kept_counts):.1f}"
        )
        for name, n in (("search and RRF", found_search), ("rerank and MMR", found_kept)):
            print(f"Found after {name}: {n}/{scored} = {n / scored:.0%}")


main()
