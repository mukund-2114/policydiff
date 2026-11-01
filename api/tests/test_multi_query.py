import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.providers.base import Response
from app.retrieval.multi_query import Rewrites, expand, extra_queries


class Chat:
    def __init__(self, queries=None, fail=False):
        self.queries, self.fail, self.calls = queries or [], fail, []

    def generate(self, messages, schema=None):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("down")
        return Response("", Rewrites(queries=self.queries), 10, 5)


class Embedder:
    model, dims = "m", 2

    def __init__(self, fail=False):
        self.fail = fail

    def embed(self, texts):
        if self.fail:
            raise RuntimeError("down")
        return [[float(len(t)), 1.0] for t in texts]


def test_no_rewrites_asked_means_no_model_call():
    chat = Chat(["x"])
    assert expand(chat, "claims", 0) == ([], 0)
    assert chat.calls == []


def test_rewrites_are_cleaned_deduplicated_and_cut_to_the_number_asked():
    chat = Chat(["  deadline   to file ", "DEADLINE to file", "claims", "reimbursement time", ""])
    out, tokens = expand(chat, "claims", 2)
    assert out == ["deadline to file", "reimbursement time"]  # the original and blanks are gone
    assert tokens == 15


def test_a_failed_call_gives_no_rewrites_instead_of_an_error():
    assert expand(Chat(fail=True), "claims", 3) == ([], 0)


def test_the_number_asked_is_in_the_prompt_and_the_query_is_marked_untrusted():
    chat = Chat(["a"])
    expand(chat, "claims", 4)
    system, user = chat.calls[0]
    assert "4 different ways" in system.content
    assert "untrusted" in system.content
    assert "<query>" in user.content


def test_rewrites_come_back_with_their_vectors():
    chat = Chat(["deadline to file", "time limit"])
    got, _ = extra_queries(chat, Embedder(), "claims", 2)
    assert [t for t, _ in got] == ["deadline to file", "time limit"]
    assert got[0][1] == [16.0, 1.0]


def test_a_failed_embedding_gives_no_extra_queries():
    got, tokens = extra_queries(Chat(["a b"]), Embedder(fail=True), "claims", 1)
    assert got == [] and tokens == 15
