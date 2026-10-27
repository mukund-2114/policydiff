import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from types import SimpleNamespace as N

from app.retrieval.funnel import apply_funnel, pair_key


def hit(name, vector):
    chunk = N(id=name, context_header=None, text=name, summary=None, embedding=vector)
    return {"chunk": chunk}


class Scores:
    """A reranker with fixed scores per chunk text."""

    def __init__(self, scores):
        self.scores = scores

    def score(self, query, docs):
        return [self.scores[d] for d in docs]


def test_pair_key_is_the_same_in_both_directions():
    assert pair_key("b", "a") == pair_key("a", "b") == "a:b"


def test_candidates_below_the_threshold_are_not_kept():
    hits = [hit("a", [1, 0]), hit("b", [0, 1])]
    out = apply_funnel("q", hits, Scores({"a": 0.9, "b": 0.2}), threshold=0.5)
    assert [(h["chunk"].id, h["kept"]) for h in out] == [("a", True), ("b", False)]
    assert out[1]["rerank_score"] == 0.2  # the score stays visible even when cut


def test_at_most_max_reranked_are_considered():
    hits = [hit(str(i), [1, i]) for i in range(5)]
    scores = Scores({str(i): 0.9 - i * 0.1 for i in range(5)})
    out = apply_funnel("q", hits, scores, max_reranked=2, keep=5, lam=1.0)
    assert [h["chunk"].id for h in out if h["kept"]] == ["0", "1"]


def test_near_copies_lose_to_a_different_candidate():
    hits = [hit("a", [1, 0]), hit("a_copy", [1, 0.01]), hit("b", [0, 1])]
    out = apply_funnel("q", hits, Scores({"a": 0.9, "a_copy": 0.85, "b": 0.7}), keep=2)
    assert [h["chunk"].id for h in out if h["kept"]] == ["a", "b"]


def test_hits_keep_their_original_order():
    hits = [hit("low", [1, 0]), hit("high", [0, 1])]
    out = apply_funnel("q", hits, Scores({"low": 0.6, "high": 0.9}))
    assert [h["chunk"].id for h in out] == ["low", "high"]


def test_no_hits_means_no_reranker_call():
    class Boom:
        def score(self, *a):
            raise AssertionError("should not be called")

    assert apply_funnel("q", [], Boom()) == []
