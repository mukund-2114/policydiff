import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest

from app.retrieval.rank import cosine, mmr, rrf
from app.retrieval.search import or_query

# rrf


def test_rrf_scores_are_one_over_k_plus_rank():
    result = dict(rrf([["a", "b"]], k=60))
    assert result["a"] == pytest.approx(1 / 61)
    assert result["b"] == pytest.approx(1 / 62)


def test_rrf_an_id_in_both_lists_beats_an_id_first_in_one():
    merged = rrf([["x", "a", "b"], ["y", "a", "c"]])
    assert merged[0][0] == "a"  # second in both lists beats first in only one
    assert merged[0][1] == pytest.approx(2 / 62)


def test_rrf_ignores_how_long_the_lists_are_and_keeps_the_top_n():
    merged = rrf([["a", "b", "c", "d"]], top=2)
    assert [i for i, _ in merged] == ["a", "b"]


def test_rrf_ties_keep_first_seen_order():
    assert [i for i, _ in rrf([["a"], ["b"]])] == ["a", "b"]


def test_rrf_of_nothing_is_empty():
    assert rrf([]) == []
    assert rrf([[], []]) == []


# cosine


def test_cosine_of_same_opposite_and_unrelated_vectors():
    assert cosine([1, 0], [2, 0]) == pytest.approx(1)
    assert cosine([1, 0], [-1, 0]) == pytest.approx(-1)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0)


def test_cosine_with_a_zero_vector_is_zero():
    assert cosine([0, 0], [1, 1]) == 0.0


# mmr

VECTORS = {"a": [1, 0], "a_copy": [1, 0.01], "b": [0, 1], "c": [1, 1]}


def test_mmr_starts_with_the_most_relevant():
    relevance = {"a": 0.9, "b": 0.5, "c": 0.7}
    assert mmr(relevance, VECTORS, keep=1) == ["a"]


def test_mmr_prefers_a_different_candidate_over_a_near_copy():
    relevance = {"a": 0.9, "a_copy": 0.85, "b": 0.6}
    # a_copy is more relevant than b but says the same thing as a, so b is picked second.
    assert mmr(relevance, VECTORS, lam=0.6, keep=2) == ["a", "b"]


def test_mmr_with_lambda_one_is_plain_top_k():
    relevance = {"a": 0.9, "a_copy": 0.85, "b": 0.6}
    assert mmr(relevance, VECTORS, lam=1.0, keep=2) == ["a", "a_copy"]


def test_mmr_returns_fewer_when_there_are_fewer_candidates():
    assert mmr({"a": 0.9}, VECTORS, keep=5) == ["a"]
    assert mmr({}, VECTORS, keep=5) == []


# the keyword query


def test_or_query_joins_unique_words_with_or():
    assert or_query("Claims must be filed; claims late!") == "claims | must | be | filed | late"


def test_or_query_drops_punctuation_that_could_break_tsquery():
    assert or_query("a:* & (b) | !c 'd'") == "a | b | c | d"


def test_or_query_of_only_punctuation_is_empty():
    assert or_query("... !!!") == ""
