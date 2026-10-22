"""Checks labels.json against the policy Markdown and figures.json.

Run:  python validate.py
Exit code 0 means every quote is real, every reference exists and the counts match the plan.
"""

import json
import sys

from corpus import HERE, load_all, squash

TYPES = {
    "numeric_mismatch",
    "obligation_conflict",
    "scope_overlap",
    "definition_mismatch",
    "outdated_reference",
}


def check_side(side: dict, docs: dict, figures: dict, where: str, errors: list[str]) -> None:
    doc = docs.get(side["doc"])
    if doc is None:
        errors.append(f"{where}: unknown document {side['doc']}")
        return
    kind, ref = side["kind"], side["ref"]
    if kind == "clause":
        text = doc.clauses.get(ref)
        if text is None:
            errors.append(f"{where}: {doc.doc_id} has no clause {ref}")
        elif squash(side["quote"]) not in squash(text):
            errors.append(f"{where}: quote not found in {doc.doc_id} {ref}: {side['quote']!r}")
    elif kind == "table":
        rows = doc.tables.get(ref)
        if rows is None:
            errors.append(f"{where}: {doc.doc_id} has no {ref}")
        elif not any(squash(side["quote"]) in squash(r) for r in rows):
            errors.append(f"{where}: no row of {doc.doc_id} {ref} contains {side['quote']!r}")
    elif kind == "figure":
        fig_id = doc.figures.get(ref)
        if fig_id != side["figure_id"]:
            errors.append(f"{where}: {doc.doc_id} {ref} shows {fig_id}, label says {side['figure_id']}")
        elif figures[fig_id]["data"].get(side["key"]) != side["value"]:
            errors.append(f"{where}: figures.json has no {side['key']} = {side['value']} in {fig_id}")
    else:
        errors.append(f"{where}: unknown kind {kind}")


def main() -> int:
    labels = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
    figures = json.loads((HERE / "figures.json").read_text(encoding="utf-8"))
    docs = load_all()
    errors: list[str] = []

    conflicts, near = labels["conflicts"], labels["near_misses"]
    seen_ids, seen_pairs = set(), set()
    for item in conflicts + near:
        where = item["id"]
        if where in seen_ids:
            errors.append(f"{where}: duplicate id")
        seen_ids.add(where)
        if item["a"]["doc"] == item["b"]["doc"]:
            errors.append(f"{where}: both sides are in {item['a']['doc']}")
        pair = frozenset(
            (f"{s['doc']}:{s['ref']}:{s.get('quote', s.get('key'))}" for s in (item["a"], item["b"]))
        )
        if pair in seen_pairs:
            errors.append(f"{where}: same pair listed twice")
        seen_pairs.add(pair)
        for s in ("a", "b"):
            check_side(item[s], docs, figures, f"{where}.{s}", errors)
    for c in conflicts:
        if c["type"] not in TYPES:
            errors.append(f"{c['id']}: unknown type {c['type']}")

    by_mode = {m: sum(1 for c in conflicts if c["modality"] == m) for m in ("text", "table", "figure")}
    if len(conflicts) != 25:
        errors.append(f"expected 25 conflicts, found {len(conflicts)}")
    if len(near) != 25:
        errors.append(f"expected 25 near misses, found {len(near)}")
    if by_mode["table"] < 5:
        errors.append(f"expected at least 5 table conflicts, found {by_mode['table']}")
    if by_mode["figure"] < 2:
        errors.append(f"expected at least 2 figure conflicts, found {by_mode['figure']}")

    for e in errors:
        print("ERROR", e)
    by_type = {t: sum(1 for c in conflicts if c["type"] == t) for t in sorted(TYPES)}
    print(f"{len(docs)} documents, {len(conflicts)} conflicts {by_mode}, {len(near)} near misses")
    print(f"by type: {by_type}")
    print("OK" if not errors else f"{len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
