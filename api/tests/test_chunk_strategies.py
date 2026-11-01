import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.pipeline.chunk import SPLITTERS, chunk_pages, split_semantic, tokens
from tests.test_chunk import block, clause, page

TRAVEL = [f"Travel booking rule number {i} applies to flights." for i in range(6)]
MEALS = [f"Meal allowance rule number {i} applies to dinners." for i in range(6)]
TEXT = " ".join(TRAVEL + MEALS)


def by_topic(sentences):
    """A made-up embedding: travel sentences point one way, meal sentences another."""
    return [[1.0, 0.0] if "Travel" in s else [0.0, 1.0] for s in sentences]


def test_the_semantic_split_cuts_where_the_topic_changes():
    pieces = split_semantic(TEXT, max_tokens=120, embed=by_topic)
    assert len(pieces) == 2
    assert all("Meal" not in s for s in [pieces[0]])
    assert all("Travel" not in s for s in [pieces[1]])


def test_a_clause_that_fits_is_never_split_or_embedded():
    def boom(_):
        raise AssertionError("should not embed")

    assert split_semantic("Short clause.", 400, boom) == ["Short clause."]


def test_semantic_pieces_respect_the_size_limit_even_inside_one_topic():
    pieces = split_semantic(" ".join(TRAVEL * 3), max_tokens=60, embed=by_topic)
    assert len(pieces) > 1
    assert all(tokens(p) <= 60 for p in pieces)


def test_no_text_is_lost_or_added_by_the_semantic_split():
    pieces = split_semantic(TEXT, max_tokens=120, embed=by_topic)
    assert " ".join(pieces).split() == TEXT.split()


def test_two_sentences_fall_back_to_the_fixed_split():
    text = "A" * 500 + ". " + "B" * 500 + "."
    assert len(split_semantic(text, 100, by_topic)) > 1


def test_semantic_chunking_without_a_way_to_embed_matches_structure():
    long_text = " ".join(f"Sentence number {i} is here." for i in range(60))
    raw = {"pages": [page(1, [block("1. A", 100, 13, True), clause("1.1", long_text, 130)])]}
    plain, _ = chunk_pages(raw, max_tokens=50, overlap_tokens=10)
    fallback, stats = chunk_pages(raw, 50, 10, strategy="semantic", embed=None)
    assert [c.text for c in fallback] == [c.text for c in plain]
    assert stats["strategy"] == "semantic"


def test_a_failing_embedder_does_not_stop_chunking():
    long_text = " ".join(f"Sentence number {i} is here." for i in range(60))
    raw = {"pages": [page(1, [block("1. A", 100, 13, True), clause("1.1", long_text, 130)])]}

    def down(_):
        raise RuntimeError("provider down")

    chunks, _ = chunk_pages(raw, 50, 10, strategy="semantic", embed=down)
    assert len(chunks) > 1


def test_semantic_chunking_in_a_document_cuts_at_the_topic_change():
    raw = {"pages": [page(1, [block("1. A", 100, 13, True), clause("1.1", TEXT, 130)])]}
    chunks, _ = chunk_pages(raw, max_tokens=120, strategy="semantic", embed=by_topic)
    assert len(chunks) == 2
    assert "Travel" in chunks[0].text and "Meal" in chunks[1].text
    assert all(c.heading_path == "1. A" for c in chunks)


def test_an_unknown_strategy_name_uses_structure():
    raw = {"pages": [page(1, [block("1. A", 100, 13, True), clause("1.1", "One.", 130)])]}
    chunks, stats = chunk_pages(raw, strategy="nonsense")
    assert [c.text for c in chunks] == ["1.1 One."]
    assert stats["strategy"] == "structure"


def test_both_strategies_are_registered():
    assert set(SPLITTERS) == {"structure", "semantic"}
