"""Reads the policy Markdown files into plain Python data.

Used by validate.py (to check the labels) and build.py (to make the PDFs).
The Markdown format is deliberately simple so this parser stays short:

  - A front matter block (--- ... ---) holds doc_id, title, version, effective, owner, collection.
  - A clause is one line that starts with its number in bold:  **4.2.1** Text of the clause.
  - A table has a caption line  **Table 4.1** Caption  followed by a Markdown table.
  - A figure is an image line followed by a caption line  **Figure 3.1** Caption.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HERE = Path(__file__).parent
POLICIES = HERE / "policies"

CLAUSE = re.compile(r"^\*\*(\d+(?:\.\d+)+)\*\*\s+(.+)$")
TABLE_CAPTION = re.compile(r"^\*\*(Table \d+(?:\.\d+)*)\*\*")
FIGURE_CAPTION = re.compile(r"^\*\*(Figure \d+(?:\.\d+)*)\*\*")
IMAGE = re.compile(r"^!\[.*\]\(figures/(\w+)\.png\)$")


@dataclass
class Doc:
    meta: dict
    clauses: dict[str, str] = field(default_factory=dict)  # "4.2.1" -> text
    tables: dict[str, list[str]] = field(default_factory=dict)  # "Table 4.1" -> rows as "a | b | c"
    figures: dict[str, str] = field(default_factory=dict)  # "Figure 3.1" -> figure_id

    @property
    def doc_id(self) -> str:
        return self.meta["doc_id"]


def load_doc(path: Path) -> Doc:
    text = path.read_text(encoding="utf-8")
    _, front, body = text.split("---", 2)
    doc = Doc(meta=yaml.safe_load(front))
    lines = body.splitlines()
    i = 0
    last_image = None
    while i < len(lines):
        line = lines[i].strip()
        if m := CLAUSE.match(line):
            doc.clauses[m.group(1)] = m.group(2)
        elif m := TABLE_CAPTION.match(line):
            rows = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("|"):
                i += 1  # skip blank line between caption and table
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):  # skip the --- separator row
                    rows.append(" | ".join(cells))
                i += 1
            doc.tables[m.group(1)] = rows[1:]  # first row is the header
            continue
        elif m := IMAGE.match(line):
            last_image = m.group(1)
        elif m := FIGURE_CAPTION.match(line):
            doc.figures[m.group(1)] = last_image
        i += 1
    return doc


def load_all() -> dict[str, Doc]:
    docs = [load_doc(p) for p in sorted(POLICIES.glob("*.md"))]
    return {d.doc_id: d for d in docs}


def squash(s: str) -> str:
    """Collapse whitespace so line wraps never break a quote check."""
    return " ".join(s.split())
