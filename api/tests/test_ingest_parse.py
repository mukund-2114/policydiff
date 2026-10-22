import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pymupdf
import pytest

from app.pipeline.parse import parse_pdf, simplify
from app.services.ingest import UploadError, register_upload


def make_pdf(path, lines):
    """A tiny PDF: a 20 point bold title, then body lines at 11 point."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), lines[0], fontsize=20, fontname="helv")
    for i, line in enumerate(lines[1:]):
        page.insert_text((72, 120 + i * 18), line, fontsize=11, fontname="helv")
    doc.save(path)
    doc.close()


def test_parse_reads_text_and_font_sizes(tmp_path):
    pdf = tmp_path / "t.pdf"
    make_pdf(pdf, ["Travel Policy", "1.1 Claims are due in 60 days."])
    raw, summary = parse_pdf(pdf)
    assert summary["pages"] == 1
    assert summary["characters"] > 20
    assert "warning" not in summary
    blocks = simplify(raw)[0]["blocks"]
    assert blocks[0]["text"] == "Travel Policy" and blocks[0]["size"] == 20.0
    assert any("60 days" in b["text"] and b["size"] == 11.0 for b in blocks)


def test_bold_flag_ignores_a_bold_clause_number_in_front_of_normal_text():
    span = lambda text, flags: {"text": text, "size": 11.0, "flags": flags, "bbox": [0, 0, 1, 1]}  # noqa: E731
    line = {"spans": [span("1.1 ", 16), span("This policy sets the rest and duty limits.", 4)]}
    heading = {"spans": [span("1. Purpose and scope", 16)]}
    raw = {
        "pages": [
            {
                "number": 1,
                "images": [],
                "tables": [],
                "blocks": [
                    {"bbox": [0, 0, 1, 1], "lines": [line]},
                    {"bbox": [0, 0, 1, 1], "lines": [heading]},
                ],
            }
        ]
    }
    clause, head = simplify(raw)[0]["blocks"]
    assert clause["bold"] is False
    assert head["bold"] is True


def test_parse_warns_when_pdf_has_no_text(tmp_path):
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(pdf)
    _, summary = parse_pdf(pdf)
    assert summary["characters"] == 0
    assert "OCR" in summary["warning"]


@pytest.mark.parametrize(
    "data, title, message",
    [
        (b"hello", "Policy", "not a PDF"),
        (b"%PDF-1.7" + b"x" * (26 * 1024 * 1024), "Policy", "larger than"),
        (b"%PDF-1.7", "   ", "required"),
        (b"%PDF-1.7", "x" * 301, "too long"),
    ],
)
def test_upload_rejects_bad_input_before_touching_the_database(data, title, message):
    with pytest.raises(UploadError, match=message):
        register_upload(
            None, None, data=data, title=title, collection="General", version_label="1.0"
        )
