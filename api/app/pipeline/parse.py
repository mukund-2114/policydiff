"""Stage 1: read the PDF and keep everything the parser can see.

PyMuPDF gives, for every page: text blocks (each made of lines and spans, with font size, font name,
bold flag and a bounding box), tables it detected, and image positions. We save all of it as JSON.
Later stages (chunking) read this file, so changing a chunking setting never needs a re-parse.

Tables: PyMuPDF finds tables drawn as full grids. Journal-style tables have only horizontal rules
(top, under the header, bottom) and no vertical lines, so a second pass finds those from the
"Table N" caption and the rules below it. Their cells are rebuilt from word positions.

Heading detection is NOT done here. This stage only records facts about the page.
"""

import re

import pymupdf

BOLD_FLAG = 16  # PyMuPDF sets this bit in a span's flags when the font is bold
CAPTION = re.compile(r"^Table\s+[A-Z]?\d+")  # "Table 1.", "Table A2"
RULE_MIN_WIDTH = 0.25  # a line must cross a quarter of the page to count as a table rule
CELL_GAP = 12  # points of blank space between two words that starts a new cell
LINE_TOLERANCE = 3  # words whose tops differ by less than this are on the same line


def find_ruled_tables(page, known: list[list[float]]) -> list[dict]:
    """Tables with horizontal rules only. Each starts at a "Table N" caption and ends at the last
    rule before the next caption. Skips any area where a grid table was already found."""
    width = page.rect.width
    rules = sorted(
        (
            d["rect"]
            for d in page.get_drawings()
            if d["rect"].height <= 2 and d["rect"].width > width * RULE_MIN_WIDTH
        ),
        key=lambda r: r.y0,
    )
    captions = sorted(
        b[1] for b in page.get_text("blocks") if b[6] == 0 and CAPTION.match(b[4].strip())
    )
    found = []
    for i, top in enumerate(captions):
        end = captions[i + 1] if i + 1 < len(captions) else page.rect.height
        mine = [r for r in rules if top < r.y0 < end]
        if len(mine) < 2:
            continue
        box = [min(r.x0 for r in mine), mine[0].y0 - 1, max(r.x1 for r in mine), mine[-1].y1 + 1]
        if any(k[0] < box[2] and box[0] < k[2] and k[1] < box[3] and box[1] < k[3] for k in known):
            continue
        words = page.get_text("words", clip=pymupdf.Rect(*box))
        lines: dict[int, list] = {}
        for w in sorted(words, key=lambda w: (round(w[1] / LINE_TOLERANCE), w[0])):
            lines.setdefault(round(w[1] / LINE_TOLERANCE), []).append(w)
        rows = []
        for line in lines.values():
            cells, last_x = [], None
            for w in sorted(line, key=lambda w: w[0]):
                if last_x is not None and w[0] - last_x < CELL_GAP:
                    cells[-1] += " " + w[4]
                else:
                    cells.append(w[4])
                last_x = w[2]
            rows.append(cells)
        if rows:
            found.append({"bbox": box, "rows": rows, "method": "rules"})
    return found


def parse_pdf(path) -> tuple[dict, dict]:
    """Returns (raw, summary). raw is saved to disk, summary is shown in the UI."""
    pages = []
    text_blocks = chars = tables_found = images_found = 0
    # Text only: leave out image bytes so the saved JSON stays small.
    # Image positions come from get_image_info.
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    with pymupdf.open(path) as pdf:
        for page in pdf:
            blocks = [b for b in page.get_text("dict", flags=flags)["blocks"] if b["type"] == 0]
            images = [{"bbox": list(i["bbox"])} for i in page.get_image_info()]
            tables = [
                {"bbox": list(t.bbox), "rows": [[c or "" for c in row] for row in t.extract()]}
                for t in page.find_tables().tables
            ]
            tables += find_ruled_tables(page, [t["bbox"] for t in tables])
            pages.append(
                {
                    "number": page.number + 1,
                    "width": page.rect.width,
                    "height": page.rect.height,
                    "blocks": blocks,
                    "images": images,
                    "tables": tables,
                }
            )
            text_blocks += len(blocks)
            chars += sum(len(s["text"]) for b in blocks for ln in b["lines"] for s in ln["spans"])
            tables_found += len(tables)
            images_found += len(images)
    summary = {
        "pages": len(pages),
        "text_blocks": text_blocks,
        "characters": chars,
        "tables": tables_found,
        "images": images_found,
    }
    if chars == 0:
        summary["warning"] = "No text found. A scanned PDF needs OCR or a vision model."
    return {"pages": pages}, summary


def simplify(raw: dict) -> list[dict]:
    """A readable view of the raw parser output, for the UI: one entry per page."""
    out = []
    for page in raw["pages"]:
        blocks = []
        for b in page["blocks"]:
            spans = [s for ln in b["lines"] for s in ln["spans"]]
            text = "\n".join("".join(s["text"] for s in ln["spans"]) for ln in b["lines"]).strip()
            if not text:
                continue
            # Bold means most of the characters are bold. A bold clause number in front of normal
            # text ("1.1 This policy...") must not make the whole block look like a heading.
            bold_chars = sum(len(s["text"]) for s in spans if s["flags"] & BOLD_FLAG)
            total_chars = sum(len(s["text"]) for s in spans) or 1
            blocks.append(
                {
                    "text": text,
                    "size": round(max(s["size"] for s in spans), 1),
                    "bold": bold_chars / total_chars > 0.5,
                    "bbox": [round(v) for v in b["bbox"]],
                }
            )
        out.append(
            {
                "number": page["number"],
                "blocks": blocks,
                "tables": page["tables"],
                "images": len(page["images"]),
            }
        )
    return out
