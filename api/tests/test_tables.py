import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pymupdf

from app.pipeline.parse import parse_pdf


def make_pdf(path, rules: bool, grid: bool = False):
    """A page with a 'Table 1.' caption, three header/body rows, and optional rules or a grid."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Table 1. Per diem by city", fontsize=11)
    rows = [("City", "Rate"), ("Toronto", "CAD 95"), ("Montreal", "CAD 85")]
    for i, (a, b) in enumerate(rows):
        page.insert_text((80, 140 + i * 20), a, fontsize=10)
        page.insert_text((300, 140 + i * 20), b, fontsize=10)
    if rules:  # top, under the header, bottom: no vertical lines
        for y in (115, 145, 195):
            page.draw_line((72, y), (520, y), width=0.8)
    if grid:
        page.draw_rect(pymupdf.Rect(72, 115, 520, 195), width=0.8)
        for y in (145, 165):
            page.draw_line((72, y), (520, y), width=0.8)
        page.draw_line((250, 115), (250, 195), width=0.8)
    doc.save(path)
    doc.close()


def test_a_table_with_only_horizontal_rules_is_found_from_its_caption(tmp_path):
    pdf = tmp_path / "rules.pdf"
    make_pdf(pdf, rules=True)
    raw, summary = parse_pdf(pdf)
    tables = raw["pages"][0]["tables"]
    assert summary["tables"] == 1 and tables[0]["method"] == "rules"
    assert tables[0]["rows"] == [["City", "Rate"], ["Toronto", "CAD 95"], ["Montreal", "CAD 85"]]


def test_a_page_without_rules_gets_no_invented_table(tmp_path):
    pdf = tmp_path / "plain.pdf"
    make_pdf(pdf, rules=False)
    _, summary = parse_pdf(pdf)
    assert summary["tables"] == 0


def test_a_grid_table_is_not_found_twice(tmp_path):
    pdf = tmp_path / "grid.pdf"
    make_pdf(pdf, rules=False, grid=True)
    raw, summary = parse_pdf(pdf)
    assert summary["tables"] == 1
    assert raw["pages"][0]["tables"][0].get("method") is None  # the grid finder got it
