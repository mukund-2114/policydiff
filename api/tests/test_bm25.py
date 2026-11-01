import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import math

from app.retrieval import bm25
from app.retrieval.bm25 import Stats


def stats(n=10, avg=10.0, **df):
    return Stats(n_docs=n, avg_len=avg, doc_freq=df)


def test_a_tsvector_is_read_into_word_counts():
    got = bm25.parse_tsvector("'claim':3,8 'day':5 'it''s':9A,10 'submit':1")
    assert got == {"claim": 2, "day": 1, "it's": 2, "submit": 1}


def test_a_rare_word_is_worth_more_than_a_common_one():
    s = stats(n=100, rare=1, common=90)
    assert bm25.idf("rare", s) > bm25.idf("common", s) > 0


def test_a_word_in_every_chunk_still_scores_above_zero():
    s = stats(n=10, everywhere=10)
    assert bm25.idf("everywhere", s) > 0


def test_the_score_is_zero_when_no_query_word_is_present():
    assert bm25.score(["claim"], {"travel": 3}, stats(), 1.2, 0.75) == 0.0


def test_repeating_a_word_helps_but_less_each_time():
    s = stats(claim=2)
    one = bm25.score(["claim"], {"claim": 1, "x": 9}, s, 1.2, 0.75)
    two = bm25.score(["claim"], {"claim": 2, "x": 8}, s, 1.2, 0.75)
    three = bm25.score(["claim"], {"claim": 3, "x": 7}, s, 1.2, 0.75)
    assert one < two < three
    assert (two - one) > (three - two)


def test_a_longer_chunk_scores_lower_for_the_same_count():
    s = stats(claim=2)
    short = bm25.score(["claim"], {"claim": 1, "x": 4}, s, 1.2, 0.75)
    long = bm25.score(["claim"], {"claim": 1, "x": 40}, s, 1.2, 0.75)
    assert short > long


def test_with_b_at_zero_length_does_not_matter():
    s = stats(claim=2)
    short = bm25.score(["claim"], {"claim": 1, "x": 4}, s, 1.2, 0.0)
    long = bm25.score(["claim"], {"claim": 1, "x": 40}, s, 1.2, 0.0)
    assert math.isclose(short, long)


def test_a_repeated_query_word_is_counted_once():
    s = stats(claim=2)
    assert bm25.score(["claim", "claim"], {"claim": 1}, s, 1.2, 0.75) == bm25.score(
        ["claim"], {"claim": 1}, s, 1.2, 0.75
    )


def test_rank_puts_the_rare_word_match_first_and_leaves_out_non_matches():
    s = stats(n=100, avg=5.0, deadline=3, the=95)
    pool = {
        "a": {"the": 4, "x": 1},
        "b": {"deadline": 1, "x": 4},
        "c": {"other": 5},
    }
    assert bm25.rank(["the", "deadline"], pool, s, limit=5) == ["b", "a"]


def test_rank_respects_the_limit():
    s = stats(claim=3)
    pool = {i: {"claim": i + 1} for i in range(5)}
    assert len(bm25.rank(["claim"], pool, s, limit=2)) == 2
