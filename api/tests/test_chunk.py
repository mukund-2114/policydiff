import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import date

from app.pipeline.chunk import chunk_pages, context_header, split_long, table_markdown, tokens

BOLD = 16


def block(text, y, size=11.0, bold=False):
    span = {"text": text, "size": size, "flags": BOLD if bold else 4, "bbox": [0, 0, 1, 1]}
    return {"bbox": [60, y, 500, y + 14], "lines": [{"spans": [span]}]}


def clause(number, text, y):
    """A numbered clause as the corpus PDFs draw it: bold number, normal text."""
    bold = {"text": number + " ", "size": 11.0, "flags": BOLD, "bbox": [0, 0, 1, 1]}
    rest = {"text": text, "size": 11.0, "flags": 4, "bbox": [0, 0, 1, 1]}
    return {"bbox": [60, y, 500, y + 14], "lines": [{"spans": [bold, rest]}]}


def page(number, blocks, tables=()):
    return {
        "number": number,
        "height": 800,
        "blocks": list(blocks),
        "tables": [{"bbox": t[0], "rows": t[1]} for t in tables],
        "images": [],
    }


def test_clauses_get_heading_paths_and_the_title_is_left_out():
    raw = {
        "pages": [
            page(
                1,
                [
                    block("Travel Policy", 60, 20, True),
                    block("1. Purpose", 100, 13, True),
                    clause("1.1", "Claims are due in 60 days.", 130),
                    clause("1.2", "Receipts are required.", 150),
                    block("2. Flights", 190, 13, True),
                    clause("2.1", "Economy is the default.", 220),
                ],
            )
        ]
    }
    chunks, stats = chunk_pages(raw)
    assert [(c.heading_path, c.text) for c in chunks] == [
        ("1. Purpose", "1.1 Claims are due in 60 days."),
        ("1. Purpose", "1.2 Receipts are required."),
        ("2. Flights", "2.1 Economy is the default."),
    ]
    assert chunks[0].page == 1 and chunks[0].boxes[0]["page"] == 1
    assert stats["chunks"] == 3 and stats["headings"] == 2


def test_a_short_label_becomes_a_subheading_and_a_follow_on_line_stays_with_its_clause():
    raw = {
        "pages": [
            page(
                1,
                [
                    block("4. Costs", 100, 13, True),
                    clause("4.1", "Hotels", 130),
                    clause("4.1.1", "Rates are capped at CAD 220.", 150),
                    block("(a) in major cities only", 170),
                    clause("4.2", "Meals are paid as a per diem.", 190),
                ],
            )
        ]
    }
    chunks, _ = chunk_pages(raw)
    assert [c.heading_path for c in chunks] == ["4. Costs > 4.1 Hotels", "4. Costs"]
    assert chunks[0].text == "4.1.1 Rates are capped at CAD 220.\n(a) in major cities only"


def test_a_table_is_its_own_chunk_and_its_cell_text_is_not_repeated():
    raw = {
        "pages": [
            page(
                1,
                [
                    block("3. Meals", 100, 13, True),
                    clause("3.1", "Rates are listed below.", 130),
                    block("Toronto", 170),  # lies inside the table area
                    clause("3.2", "Alcohol is not paid.", 300),
                ],
                tables=[([50, 160, 510, 200], [["City", "Rate"], ["Toronto", "CAD 95"]])],
            )
        ]
    }
    chunks, _ = chunk_pages(raw)
    assert [c.kind for c in chunks] == ["text", "table", "text"]
    assert chunks[1].text.startswith("| City | Rate |")
    assert "CAD 95" in chunks[1].text
    assert not any("Toronto" == c.text for c in chunks)


def test_repeated_footers_and_page_numbers_are_dropped():
    def footer(n):
        return {**block(f"Northwind Air Policy {n}", 770, 9), "bbox": [60, 770, 500, 784]}

    raw = {
        "pages": [
            page(1, [block("1. A", 100, 13, True), clause("1.1", "One.", 130), footer(1)]),
            page(2, [clause("1.2", "Two.", 100), footer(2)]),
        ]
    }
    chunks, stats = chunk_pages(raw)
    assert [c.text for c in chunks] == ["1.1 One.", "1.2 Two."]
    assert chunks[1].page == 2
    assert stats["header_footer_blocks_dropped"] == 2


def test_a_long_clause_is_split_at_sentences_with_overlap():
    sentences = [f"Sentence number {i} is here." for i in range(40)]
    pieces = split_long(" ".join(sentences), max_tokens=50, overlap_tokens=10)
    assert len(pieces) > 1
    assert all(tokens(p) <= 50 for p in pieces)
    # the last sentence of one piece is repeated at the start of the next
    last = pieces[0].split(". ")[-1].rstrip(".")
    assert pieces[1].startswith(last) or last in pieces[1][:60]
    assert split_long("Short.", 50, 10) == ["Short."]


def test_split_pieces_are_marked_in_the_chunk_list():
    long_text = " ".join(f"Sentence number {i} is here." for i in range(60))
    raw = {"pages": [page(1, [block("1. A", 100, 13, True), clause("1.1", long_text, 130)])]}
    chunks, stats = chunk_pages(raw, max_tokens=50, overlap_tokens=10)
    assert len(chunks) > 1 and all(c.split for c in chunks)
    assert stats["split_clauses"] == 1


def test_table_markdown_and_context_header():
    assert table_markdown([["A", "B|C"], ["1", "2"]]) == "| A | B/C |\n| --- | --- |\n| 1 | 2 |"
    assert context_header("Travel Policy", "2.0", date(2025, 3, 1), "5. Claims") == (
        "Travel Policy, version 2.0, effective 2025-03-01. Section: 5. Claims"
    )
    assert context_header("Travel Policy", "2.0", None, None) == "Travel Policy, version 2.0."
