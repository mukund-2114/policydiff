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


def test_llm_reranker_uses_chat_scores():
    class _Score(BaseModel):
        score: float

    class Fake:
        def generate(self, messages: list[Message], schema=None):
            same = "30 days" in messages[-1].content.split("<passage_b>")[1]
            return Response("", schema(score=0.9 if same else 0.1), 0, 0)

    scores = LLMReranker(Fake()).score("claims within 30 days", ["due in 30 days", "pets allowed"])
    assert scores == [0.9, 0.1]
