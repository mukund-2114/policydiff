import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from pydantic import BaseModel

from app import auth
from app.providers.base import Message, ProviderError, Response
from app.providers.registry import ChatCfg, EgressCfg, EmbedCfg, ModelsConfig, check_egress
from app.providers.rerank import LLMReranker


def cfg(provider="openai", base_url=None, allow_cloud=False):
    return ModelsConfig(
        chat=ChatCfg(provider=provider, model="m", base_url=base_url),
        embed=EmbedCfg(
            provider="ollama" if provider == "ollama" else "openai",
            model="e",
            dims=8,
            base_url=base_url,
        ),
        egress=EgressCfg(allow_cloud=allow_cloud),
    )


def test_cloud_provider_refused_when_cloud_not_allowed():
    with pytest.raises(ProviderError):
        check_egress(cfg("openai"))


def test_cloud_provider_allowed_when_enabled():
    check_egress(cfg("openai", allow_cloud=True))


def test_private_ollama_allowed_without_cloud():
    check_egress(cfg("ollama", base_url="http://ollama:11434"))
    check_egress(cfg("ollama", base_url="http://192.168.1.20:11434"))


def test_public_ollama_url_refused_without_cloud():
    with pytest.raises(ProviderError):
        check_egress(cfg("ollama", base_url="https://models.example.com"))


def test_session_token_round_trip_and_tamper():
    import uuid

    uid = uuid.uuid4()
    token = auth.make_session_token(uid)
    assert auth.read_session_token(token) == uid
    assert auth.read_session_token(token + "x") is None
    assert auth.read_session_token("garbage") is None


def test_password_hash_verifies():
    h = auth.hash_password("correct horse")
    assert auth.verify_password(h, "correct horse")
    assert not auth.verify_password(h, "wrong")


def test_llm_reranker_scores_all_candidates_in_one_call():
    class _Scores(BaseModel):
        scores: list[float]

    calls = []

    class Fake:
        def generate(self, messages: list[Message], schema=None):
            calls.append(messages)
            n = messages[-1].content.count("<candidate ")
            return Response("", schema(scores=[0.9] + [0.1] * (n - 1)), 0, 0)

    scores = LLMReranker(Fake()).score("claims within 30 days", ["due in 30 days", "pets allowed"])
    assert scores == [0.9, 0.1]
    assert len(calls) == 1  # one call for the whole list, not one per candidate


def test_llm_reranker_rejects_a_wrong_number_of_scores():
    class Fake:
        def generate(self, messages, schema=None):
            return Response("", schema(scores=[0.5]), 0, 0)

    with pytest.raises(ProviderError):
        LLMReranker(Fake()).score("q", ["a", "b"])


def test_llm_reranker_clamps_scores_into_zero_to_one():
    class Fake:
        def generate(self, messages, schema=None):
            return Response("", schema(scores=[1.4, -0.2]), 0, 0)

    assert LLMReranker(Fake()).score("q", ["a", "b"]) == [1.0, 0.0]


def test_local_reranker_squeezes_raw_scores_into_zero_to_one():
    from app.providers.local_rerank import LocalReranker

    r = LocalReranker("m")
    r.__dict__["_encoder"] = type("E", (), {"rerank": lambda self, q, d: [-8.0, 0.0, 8.0]})()
    low, mid, high = r.score("q", ["a", "b", "c"])
    assert low < 0.01 and mid == 0.5 and high > 0.99


def test_cohere_reranker_puts_each_score_on_its_document(monkeypatch):
    from app.providers import cohere_rerank

    class Resp:
        status_code = 200

        def json(self):  # Cohere answers best first, with the index of each document
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.8},
                    {"index": 0, "relevance_score": 0.2},
                ]
            }

    monkeypatch.setattr(cohere_rerank.httpx, "post", lambda *a, **k: Resp())
    assert cohere_rerank.CohereReranker("m", "key").score("q", ["a", "b"]) == [0.2, 0.8]


def test_cohere_needs_a_key_and_counts_as_cloud():
    from app.providers.cohere_rerank import CohereReranker
    from app.providers.registry import RerankCfg

    with pytest.raises(ProviderError):
        CohereReranker("m", "")
    c = cfg("ollama")
    c.rerank = RerankCfg(provider="cohere")
    with pytest.raises(ProviderError):
        check_egress(c)
