import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from pydantic import ValidationError

from app.providers import registry
from app.providers.model_list import keep_openai, list_models
from app.providers.openai_adapter import OpenAIEmbedder
from app.providers.registry import ChatCfg, EgressCfg, EmbedCfg, ModelsConfig
from app.routers.settings import SettingsIn, _needed_keys
from app.services import runtime


def test_openai_chat_models_are_kept_and_the_rest_of_the_catalogue_is_not():
    chat = ["gpt-5-mini", "gpt-4o", "o3", "chatgpt-4o-latest"]
    other = [
        "text-embedding-3-small",
        "whisper-1",
        "gpt-4o-audio-preview",
        "gpt-4o-realtime-preview",
        "dall-e-3",
        "gpt-image-1",
        "gpt-3.5-turbo-instruct",
        "omni-moderation-latest",
        "gpt-4o-mini-tts",
    ]
    assert all(keep_openai(m, "chat") for m in chat)
    assert not any(keep_openai(m, "chat") for m in other)


def test_embedding_models_are_listed_for_the_embedding_job_only():
    assert keep_openai("text-embedding-3-large", "embed")
    assert not keep_openai("gpt-5-mini", "embed")
    assert not keep_openai("text-embedding-3-large", "chat")


def test_without_a_key_the_list_says_why_instead_of_failing():
    models, message = list_models("openai", "chat", key="")
    assert models == [] and "key" in message
    models, message = list_models("anthropic", "chat", key="")
    assert models == [] and "key" in message


def test_anthropic_has_no_embedding_models_and_bedrock_has_no_list():
    assert list_models("anthropic", "embed", key="k")[0] == []
    models, message = list_models("bedrock", "chat")
    assert models == [] and "Type" in message


def test_a_server_address_is_needed_to_list_an_openai_compatible_server():
    models, message = list_models("openai_compatible", "chat")
    assert models == [] and "address" in message


def cfg():
    return ModelsConfig(
        chat=ChatCfg(provider="openai", model="m1"),
        embed=EmbedCfg(provider="openai", model="text-embedding-3-small", dims=1536),
        egress=EgressCfg(allow_cloud=True),
    )


def test_a_saved_embedding_choice_wins_but_the_vector_size_stays(monkeypatch):
    monkeypatch.setattr(registry, "load_config", cfg)
    monkeypatch.setattr(runtime, "stored_data", lambda: {})
    got = registry.effective_config({"embed": {"provider": "openai", "model": "big"}})
    assert (got.embed.model, got.embed.dims) == ("big", 1536)
    assert registry.effective_config({}).embed.model == "text-embedding-3-small"


def test_the_embedding_pick_only_allows_providers_that_embed():
    with pytest.raises(ValidationError):
        SettingsIn(embed={"provider": "anthropic", "model": "x"})
    assert SettingsIn(embed={"provider": "ollama", "model": "x"}).embed.provider == "ollama"


def test_an_openai_embedding_choice_needs_the_openai_key():
    assert _needed_keys({"embed": {"provider": "openai", "model": "x"}}) == {"openai"}
    assert _needed_keys({"embed": {"provider": "ollama", "model": "x"}}) == set()


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class Item:
            embedding = [0.0] * 1536

        return type("R", (), {"data": [Item() for _ in kwargs["input"]]})


def embedder(model):
    e = OpenAIEmbedder(model, 1536, "sk-x")
    fake = FakeEmbeddings()
    e._client = type("C", (), {"embeddings": fake})()
    return e, fake


def test_the_large_model_is_asked_for_vectors_that_fit_the_column():
    e, fake = embedder("text-embedding-3-large")
    e.embed(["a"])
    assert fake.calls[0]["dimensions"] == 1536


def test_an_older_model_is_not_sent_a_size_it_does_not_accept():
    e, fake = embedder("text-embedding-ada-002")
    e.embed(["a"])
    assert "dimensions" not in fake.calls[0]
