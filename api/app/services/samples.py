"""The Northwind Air demo corpus: the Markdown policies and the answer key, read straight from disk.

The corpus lives in evals/northwind (mounted read-only at SAMPLES_DIR). Nothing here touches the
database or the upload pipeline. It exists so the policies can be read, compared and checked against
the answer key inside the app. If the folder is missing, the sample features switch themselves off.
"""

import json
import re
from pathlib import Path

import yaml

from app.config import get_settings

DOC_ID = re.compile(r"^[A-Z]{3}-\d{3}$")
FIGURE_NAME = re.compile(r"^[a-z_]+\.png$")


def root() -> Path:
    return Path(get_settings().samples_dir)


def available() -> bool:
    return (root() / "labels.json").exists() and (root() / "policies").is_dir()


def _split(md: Path) -> tuple[dict, str]:
    _, front, body = md.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(front), body.strip()


def _meta(m: dict) -> dict:
    return {
        "doc_id": m["doc_id"],
        "title": m["title"],
        "version": str(m["version"]),
        "effective": str(m["effective"]),
        "owner": m["owner"],
        "collection": m["collection"],
    }


def policies() -> list[dict]:
    return [_meta(_split(p)[0]) for p in sorted((root() / "policies").glob("*.md"))]


def policy(doc_id: str) -> dict | None:
    """Metadata plus the Markdown body of one policy. None when the id is unknown."""
    if not DOC_ID.match(doc_id):  # the id becomes part of a file name, so only accept the exact shape
        return None
    path = root() / "policies" / f"{doc_id}.md"
    if not path.exists():
        return None
    meta, body = _split(path)
    return {**_meta(meta), "markdown": body}


def figure_path(name: str) -> Path | None:
    if not FIGURE_NAME.match(name):
        return None
    path = root() / "figures" / name
    return path if path.exists() else None


def answer_key() -> dict:
    """labels.json, with a readable text for each side and the policy title."""
    labels = json.loads((root() / "labels.json").read_text(encoding="utf-8"))
    figures = json.loads((root() / "figures.json").read_text(encoding="utf-8"))
    titles = {p["doc_id"]: p["title"] for p in policies()}

    def side(s: dict) -> dict:
        unit = figures.get(s.get("figure_id", ""), {}).get("unit", "")
        text = s.get("quote") or f"{s['key']}: {s['value']} {unit}".strip()
        return {"doc": s["doc"], "title": titles[s["doc"]], "ref": s["ref"], "kind": s["kind"], "text": text}

    def convert(item: dict) -> dict:
        out = {"id": item["id"], "note": item["note"], "a": side(item["a"]), "b": side(item["b"])}
        if "type" in item:
            out.update(type=item["type"], modality=item["modality"])
        return out

    return {
        "conflicts": [convert(c) for c in labels["conflicts"]],
        "near_misses": [convert(n) for n in labels["near_misses"]],
    }
