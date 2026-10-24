import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.pipeline.embed import MAX_CHARS, embedding_input


def test_the_context_line_goes_in_front_of_the_text():
    out = embedding_input(
        "Expense Policy, version 3.1. Section: 5. Claims", "5.1 Claims are due in 30 days."
    )
    assert out == "Expense Policy, version 3.1. Section: 5. Claims\n5.1 Claims are due in 30 days."


def test_a_chunk_without_a_context_line_is_embedded_as_is():
    assert embedding_input(None, "Some text") == "Some text"


def test_a_summary_replaces_the_raw_text_when_there_is_one():
    assert (
        embedding_input("Header", "| a | b |", summary="Per diem by city")
        == "Header\nPer diem by city"
    )


def test_very_long_input_is_cut_to_fit_the_model():
    assert len(embedding_input("H", "x" * (MAX_CHARS * 2))) == MAX_CHARS
