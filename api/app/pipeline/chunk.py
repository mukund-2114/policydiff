"""Stage 2: cut the parsed pages into clauses, each with its heading path.

Pure functions only: raw parser output in, a list of ChunkDraft out. No database, no files, so the
rules can be read and tested in one place. The job in tasks.py does the saving.

The rules, in the order they run:
  1. Drop page headers and footers (text that sits in the page margin and repeats, or page numbers).
  2. Work out the body font size: the size most characters are written in.
  3. A heading is a block that is larger than the body text, or bold and short. Bigger size means a
     higher level. A single line in the largest size, above the section headings, is the title
     and is left out of paths.
  4. A numbered clause ("4.2.1 ...") starts a new chunk. Text that follows without a number (a
     list, a second paragraph) stays with the clause above it.
     A short clause that only labels the numbered clauses under it ("4.1 Hotels" before "4.1.1")
     is treated as a sub-heading and goes into the path instead of becoming a chunk.
  5. A table becomes its own chunk, written as Markdown. Text the parser found inside the table
     area is dropped so it is not counted twice.
  6. A chunk longer than the limit is split at sentence ends, repeating a little text (overlap)
     at the start of each next piece so no sentence loses its context.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from app.pipeline.parse import simplify

CLAUSE_START = re.compile(r"^(\d+(?:\.\d+)+)\.?\s")  # "1.1 ", "4.2.1. " but not "1. Purpose"
SUBHEAD_LEVEL = 100  # numbered sub-headings always rank below headings found by font size
LABEL_MAX_CHARS = 60  # a clause this short, with no full stop, is a label and not a rule
PAGE_NUMBER = re.compile(r"^(page\s+)?#( of #)?$", re.IGNORECASE)  # digits are replaced by #
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
MARGIN = 0.08  # the top and bottom 8% of a page count as header and footer area
CHARS_PER_TOKEN = 4  # a rough rule that holds for English; avoids needing a tokenizer


@dataclass
class ChunkDraft:
    kind: str  # text or table
    heading_path: str | None
    text: str
    page: int
    boxes: list[dict] = field(default_factory=list)  # [{"page": 1, "bbox": [x0, y0, x1, y1]}]
    split: bool = False  # true when this piece was cut from a longer clause


def tokens(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def table_markdown(rows: list[list[str]]) -> str:
    rows = [[c.replace("\n", " ").replace("|", "/").strip() for c in r] for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def context_header(title: str, version_label: str, effective_from, heading_path: str | None) -> str:
    """One line placed before the text when it is embedded, so a loose sentence keeps its place."""
    parts = [f"{title}, version {version_label}"]
    if effective_from:
        parts.append(f"effective {effective_from}")
    header = ", ".join(parts) + "."
    return f"{header} Section: {heading_path}" if heading_path else header


def split_long(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Cut at sentence ends. Each piece after the first starts with the end of the one before."""
    if tokens(text) <= max_tokens:
        return [text]
    limit, keep = max_tokens * CHARS_PER_TOKEN, overlap_tokens * CHARS_PER_TOKEN
    sentences = []
    for s in SENTENCE_END.split(text):
        # A "sentence" longer than the limit (no full stops) is cut by length.
        sentences += [s[i : i + limit] for i in range(0, len(s), limit)] or [s]
    pieces, current = [], []
    for s in sentences:
        if current and len(" ".join(current + [s])) > limit:
            pieces.append(" ".join(current))
            tail, size = [], 0
            for prev in reversed(current):  # carry the last sentences over, up to the overlap
                if size + len(prev) > keep:
                    break
                tail.insert(0, prev)
                size += len(prev)
            current = tail
        current.append(s)
    pieces.append(" ".join(current))
    return pieces


def _margin_noise(pages: list[dict], simple: list[dict]) -> set[tuple[int, int]]:
    """(page index, block index) of headers, footers and page numbers."""
    zones, seen = {}, Counter()
    for pi, (raw, page) in enumerate(zip(pages, simple, strict=True)):
        h = raw["height"]
        for bi, b in enumerate(page["blocks"]):
            if b["bbox"][3] < h * MARGIN or b["bbox"][1] > h * (1 - MARGIN):
                key = re.sub(r"\d+", "#", " ".join(b["text"].split())).lower()
                zones[(pi, bi)] = key
                seen[(key, pi)] = 1
    pages_per_key = Counter(key for key, _ in seen)
    return {pos for pos, key in zones.items() if pages_per_key[key] >= 2 or PAGE_NUMBER.match(key)}


def chunk_pages(raw: dict, max_tokens: int = 400, overlap_tokens: int = 50) -> tuple[list, dict]:
    """Returns (chunks, stats). stats is shown on the pipeline page."""
    simple = simplify(raw)
    noise = _margin_noise(raw["pages"], simple)

    # Body size: the font size that most characters use.
    weight = Counter()
    for page in simple:
        for b in page["blocks"]:
            weight[b["size"]] += len(b["text"])
    body = weight.most_common(1)[0][0] if weight else 11.0

    def is_heading(b: dict) -> bool:
        flat = " ".join(b["text"].split())
        if CLAUSE_START.match(flat):
            return False
        return b["size"] >= body + 1 or (b["bold"] and len(flat) <= 100)

    sizes = sorted({b["size"] for p in simple for b in p["blocks"] if is_heading(b)}, reverse=True)
    top = [b for p in simple for b in p["blocks"] if sizes and b["size"] == sizes[0]]
    # The title is the one block in a size nobody else uses, above the section headings.
    title = top[0] if len(top) == 1 and len(sizes) > 1 else None
    levels = [s for s in sizes if not (title and s == title["size"])]

    def level(b: dict) -> int:
        return levels.index(b["size"]) if b["size"] in levels else len(levels)  # bold-only is last

    chunks: list[ChunkDraft] = []
    stack: list[tuple[int, str]] = []  # (level, heading text)
    cur: ChunkDraft | None = None
    cur_number = ""
    seen_heading = False
    stats = Counter()

    def end_clause(number: str):
        """Called when a numbered clause starts. A short label that the new clause sits under
        becomes a sub-heading, and sub-headings the new clause no longer sits under are closed."""
        nonlocal cur
        if cur and cur_number and number.startswith(cur_number + "."):
            label = " ".join(cur.text.split())
            if len(label) <= LABEL_MAX_CHARS and not label.endswith("."):
                depth = cur_number.count(".")
                while stack and stack[-1][0] >= SUBHEAD_LEVEL + depth:
                    stack.pop()
                stack.append((SUBHEAD_LEVEL + depth, label))
                stats["sub_headings"] += 1
                cur = None
        flush()
        depth = number.count(".")
        while stack and stack[-1][0] >= SUBHEAD_LEVEL + depth:
            stack.pop()

    def flush():
        nonlocal cur
        if cur and cur.text.strip():
            pieces = split_long(cur.text.strip(), max_tokens, overlap_tokens)
            for piece in pieces:
                chunks.append(
                    ChunkDraft(
                        "text", cur.heading_path, piece, cur.page, cur.boxes, split=len(pieces) > 1
                    )
                )
            if len(pieces) > 1:
                stats["split_clauses"] += 1
        cur = None

    for pi, page in enumerate(simple):
        items = []
        for bi, b in enumerate(page["blocks"]):
            if (pi, bi) in noise:
                stats["header_footer_blocks_dropped"] += 1
                continue
            cx, cy = (b["bbox"][0] + b["bbox"][2]) / 2, (b["bbox"][1] + b["bbox"][3]) / 2
            if any(
                t["bbox"][0] <= cx <= t["bbox"][2] and t["bbox"][1] <= cy <= t["bbox"][3]
                for t in page["tables"]
            ):
                continue  # this text belongs to a table and is read from the table instead
            items.append((b["bbox"][1], b["bbox"][0], "block", b))
        items += [(t["bbox"][1], t["bbox"][0], "table", t) for t in page["tables"]]

        for _, _, what, item in sorted(items, key=lambda i: i[:2]):
            path = " > ".join(h for _, h in stack) or None
            if what == "table":
                flush()
                text = table_markdown(item["rows"])
                if text:
                    box = [{"page": page["number"], "bbox": item["bbox"]}]
                    chunks.append(ChunkDraft("table", path, text, page["number"], box))
                continue
            flat = " ".join(item["text"].split())
            box = {"page": page["number"], "bbox": item["bbox"]}
            if title is not None and item is title:
                continue
            if not seen_heading and not is_heading(item) and item["size"] < body - 0.5:
                stats["front_matter_dropped"] += 1  # e.g. the "Document X, version Y" line
                continue
            if is_heading(item):
                seen_heading = True
                flush()
                lv = level(item)
                while stack and stack[-1][0] >= lv:
                    stack.pop()
                stack.append((lv, flat))
                stats["headings"] += 1
            elif m := CLAUSE_START.match(flat):
                end_clause(m.group(1))
                path = " > ".join(h for _, h in stack) or None  # the stack may have just changed
                text = item["text"].replace("\n", " ")
                cur = ChunkDraft("text", path, text, page["number"], [box])
                cur_number = m.group(1)
            elif cur is None:
                text = item["text"].replace("\n", " ")
                cur = ChunkDraft("text", path, text, page["number"], [box])
                cur_number = ""
            else:  # a follow-on paragraph or list line: keep it with its clause
                cur.text += "\n" + item["text"]
                cur.boxes.append(box)
    flush()

    stats["chunks"] = len(chunks)
    stats["table_chunks"] = sum(c.kind == "table" for c in chunks)
    stats["longest_tokens"] = max((tokens(c.text) for c in chunks), default=0)
    return chunks, dict(stats)
