"""Finding precision and recall: do the scan's findings match the planted conflicts?

Run a scan of every Northwind version first (the Scan button, once per document). Then run this
inside the api container, where the database is:

    docker compose --env-file ../.env exec -T api python - < ../evals/judge_eval.py

It reads what the scans already stored and calls no model, so it costs nothing and can be repeated.

Each labelled side is found among the stored chunks, as in candidate_recall.py. A finding is then
sorted by the pair of chunks it joins:
  - true: the pair is a planted conflict
  - near miss: the pair is a labelled near miss, so it is a certain false alarm
  - unlabelled: the pair is in neither list. Counted as false in the score (the strict reading)
    and listed so you can check by hand whether the labels missed a real conflict.
Recall is the share of scorable planted conflicts that have a finding. For each miss it says whether
the pair never reached the judge (a funnel miss), or the judge said no (a judge miss).
The last table repeats the score at several confidence cut-offs, to pick the one to show reviewers.
"""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models import (
    Chunk,
    Document,
    DocumentVersion,
    Finding,
    PairJudgment,
    Scan,
    Workspace,
)
from app.retrieval.funnel import pair_key

LABELS = "/samples/labels.json"
CUTOFFS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9)


def squash(text):
    """Collapse every run of whitespace, because the PDF wraps a clause across lines."""
    return " ".join(text.split())


def find_chunk(chunks, side):
    """The chunk of side['doc'] that holds the quoted clause or table row, or None."""
    if side["kind"] == "figure":
        # The figure chunk of that document whose reading mentions the labelled value.
        for c in chunks.get(side["doc"], []):
            if c.kind == "figure" and str(side["value"]) in c.text:
                return c
        return None
    is_table = side["kind"] == "table"
    wanted = (
        [squash(c) for c in side["quote"].split(" | ")]
        if is_table
        else [squash(side["quote"])]
    )
    for c in chunks.get(side["doc"], []):
        if (c.kind == "table") == is_table and all(w in squash(c.text) for w in wanted):
            return c
    return None


def label_keys(chunks, items):
    """pair_key -> label id, for the labels whose two sides are both found."""
    keys = {}
    for item in items:
        a, b = (find_chunk(chunks, item[s]) for s in "ab")
        if a and b:
            keys[pair_key(a.id, b.id)] = item["id"]
    return keys


def score(findings, truth, n_conflicts):
    """Precision and recall for one list of findings. truth maps pair_key to a conflict id."""
    hits = [f for f in findings if f["key"] in truth]
    found = {truth[f["key"]] for f in hits}
    precision = len(hits) / len(findings) if findings else 0.0
    return precision, len(found) / n_conflicts, len(findings), len(found)


def main():
    data = json.load(open(LABELS, encoding="utf-8"))
    with Session(get_engine()) as db:
        ws = db.scalar(select(Workspace.id))
        rows = db.execute(
            select(Chunk, Document.title)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(DocumentVersion.status == "ready", Chunk.workspace_id == ws)
        ).all()
        chunks, ref = {}, {}
        for c, title in rows:
            chunks.setdefault(title, []).append(c)
            ref[c.id] = f"{title} {c.heading_path or ''}".strip()

        # Only documents that were scanned can produce findings, so only conflicts and near
        # misses that touch one of them are scored. A scan judges a pair from its own side, so
        # one scanned side is enough.
        scanned = set(
            db.scalars(
                select(Document.title)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .join(Scan, Scan.scope == func.concat("version:", DocumentVersion.id))
                .where(Scan.status == "done", Scan.workspace_id == ws)
            )
        )
        print(f"Scanned documents: {', '.join(sorted(scanned)) or 'none'}")
        data["conflicts"] = [
            c for c in data["conflicts"] if {c["a"]["doc"], c["b"]["doc"]} & scanned
        ]
        data["near_misses"] = [
            c for c in data["near_misses"] if {c["a"]["doc"], c["b"]["doc"]} & scanned
        ]
        truth = label_keys(chunks, data["conflicts"])
        misses = label_keys(chunks, data["near_misses"])
        n_conflicts = len(truth)

        judged = {
            j.pair_key: j
            for j in db.scalars(
                select(PairJudgment).where(PairJudgment.workspace_id == ws)
            )
        }
        findings = []
        for f, j in db.execute(
            select(Finding, PairJudgment)
            .join(PairJudgment, PairJudgment.id == Finding.judgment_id)
            .where(Finding.workspace_id == ws)
        ).all():
            findings.append(
                {
                    "key": j.pair_key,
                    "type": f.type,
                    "confidence": f.confidence,
                    "a": j.chunk_a,
                    "b": j.chunk_b,
                }
            )

        print(f"Scorable planted conflicts: {n_conflicts} of {len(data['conflicts'])} ")
        print(f"Pairs judged: {len(judged)}   Findings: {len(findings)}")
        unverified = sum(j.verdict == "unverified" for j in judged.values())
        print(f"Dropped for a quote not in the text: {unverified}\n")

        by_kind = {}  # modality -> [found, scored]
        print("Planted conflicts")
        for item in data["conflicts"]:
            key = next((k for k, v in truth.items() if v == item["id"]), None)
            if key is None:
                print(f"  {item['id']} {item['type']:20} SKIP (side not found)")
                continue
            if any(f["key"] == key for f in findings):
                state = "found"
            elif key in judged:
                state = f"JUDGE MISS (verdict {judged[key].verdict})"
            else:
                state = "FUNNEL MISS (never judged)"
            tally = by_kind.setdefault(item["modality"], [0, 0])
            tally[0] += state == "found"
            tally[1] += 1
            print(f"  {item['id']} {item['type']:20} {item['modality']:7} {state}")

        print()
        print("Found by kind")
        for kind, (got, of) in sorted(by_kind.items()):
            print(f"  {kind:7} {got} of {of}")

        unlabelled = [f for f in findings if f["key"] not in truth]
        print("\nFindings that are not planted conflicts")
        for f in sorted(unlabelled, key=lambda f: -f["confidence"]):
            tag = (
                f"near miss {misses[f['key']]}" if f["key"] in misses else "unlabelled"
            )
            print(
                f"  {f['confidence']:.2f} {f['type']:20} {tag:16} {ref[f['a']]} <> {ref[f['b']]}"
            )

        print("\nScore by confidence cut-off")
        print("  cut-off  shown  true  precision  recall")
        for cut in CUTOFFS:
            shown = [f for f in findings if f["confidence"] >= cut]
            p, r, n, k = score(shown, truth, n_conflicts)
            print(f"  {cut:>6.2f}  {n:>5}  {k:>4}  {p:>9.0%}  {r:>6.0%}")


main()
