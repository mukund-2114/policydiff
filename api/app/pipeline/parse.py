"""Stage 1: read the PDF and keep everything the parser can see.

PyMuPDF gives, for every page: text blocks (each made of lines and spans, with font size, font name,
bold flag and a bounding box), tables it detected, and image positions. We save all of it as JSON.
Later stages (chunking) read this file, so changing a chunking setting never needs a re-parse.

Heading detection is NOT done here. This stage only records facts about the page.
"""

import pymupdf

BOLD_FLAG = 16  # PyMuPDF sets this bit in a span's flags when the font is bold


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
