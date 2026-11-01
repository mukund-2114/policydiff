import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest
from pydantic import BaseModel

from app.providers import registry
from app.providers.base import Message, ProviderError
from app.providers.bedrock_adapter import BedrockChat
from app.providers.registry import ChatCfg, EgressCfg, EmbedCfg, ModelsConfig, check_egress


class Answer(BaseModel):
    verdict: str


class FakeBedrock:
    def __init__(self, content):
        self.content, self.sent = content, None

    def converse(self, **kwargs):
        self.sent = kwargs
        return {
            "output": {"message": {"content": self.content}},
            "usage": {"inputTokens": 12, "outputTokens": 3},
        }


def test_bedrock_sends_system_text_and_images_and_counts_tokens():
    fake = FakeBedrock([{"text": "hello"}])
    chat = BedrockChat("some.model", client=fake)
    r = chat.generate([Message("system", "be brief"), Message("user", "hi", images=[b"png"])])
    assert fake.sent["system"] == [{"text": "be brief"}]
    user = fake.sent["messages"][0]
    assert user["role"] == "user"
    assert user["content"][1] == {"image": {"format": "png", "source": {"bytes": b"png"}}}
    assert (r.text, r.input_tokens, r.output_tokens) == ("hello", 12, 3)


def test_bedrock_returns_a_schema_answer_from_a_forced_tool_call():
    fake = FakeBedrock([{"toolUse": {"name": "result", "input": {"verdict": "conflict"}}}])
    r = BedrockChat("m", client=fake).generate([Message("user", "x")], schema=Answer)
    assert r.parsed == Answer(verdict="conflict")
    assert fake.sent["toolConfig"]["toolChoice"] == {"tool": {"name": "result"}}


def cfg(provider, base_url=None, allow_cloud=False):
    return ModelsConfig(
        chat=ChatCfg(provider=provider, model="m", base_url=base_url),
        embed=EmbedCfg(provider="ollama", model="e", dims=8, base_url="http://ollama:11434"),
        egress=EgressCfg(allow_cloud=allow_cloud),
    )


def test_bedrock_counts_as_cloud():
    with pytest.raises(ProviderError):
        check_egress(cfg("bedrock"))
    check_egress(cfg("bedrock", allow_cloud=True))


def test_an_openai_compatible_server_on_a_private_address_needs_no_cloud():
    check_egress(cfg("openai_compatible", base_url="http://192.168.1.20:8000/v1"))
    with pytest.raises(ProviderError):
        check_egress(cfg("openai_compatible", base_url="https://api.example.com/v1"))


def test_openai_compatible_needs_an_address():
    with pytest.raises(ProviderError):
        registry.build_chat(ChatCfg(provider="openai_compatible", model="m"))


def test_saving_an_openai_compatible_choice_without_an_address_is_refused(monkeypatch):
    from app.services import runtime

    monkeypatch.setattr(registry, "load_config", lambda: cfg("openai", allow_cloud=True))
    monkeypatch.setattr(runtime, "stored_data", lambda: {})
    with pytest.raises(ProviderError):
        registry.effective_config({"chat": {"provider": "openai_compatible", "model": "m"}})
    ok = registry.effective_config(
        {"chat": {"provider": "openai_compatible", "model": "m", "base_url": "http://h:8000/v1"}}
    )
    assert ok.chat.base_url == "http://h:8000/v1"
