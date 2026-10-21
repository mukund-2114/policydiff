"""Reads models.yaml and builds the adapters. Enforces the egress rule in code."""

import ipaddress
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel

from app.config import get_settings
from app.providers.anthropic_adapter import AnthropicChat
from app.providers.base import ChatModel, Embedder, ProviderError, Reranker
from app.providers.ollama_adapter import OllamaChat, OllamaEmbedder
from app.providers.openai_adapter import OpenAIChat, OpenAIEmbedder
from app.providers.rerank import LLMReranker

CLOUD_PROVIDERS = {"openai", "anthropic"}


class ChatCfg(BaseModel):
    provider: Literal["openai", "anthropic", "ollama"]
    model: str
    base_url: str | None = None


class EmbedCfg(BaseModel):
    provider: Literal["openai", "ollama"]
    model: str
    dims: int
    base_url: str | None = None


class RerankCfg(BaseModel):
    provider: Literal["llm"] = "llm"


class EgressCfg(BaseModel):
    allow_cloud: bool = False
    log_payloads: bool = False


class ModelsConfig(BaseModel):
    chat: ChatCfg
    embed: EmbedCfg
    rerank: RerankCfg = RerankCfg()
    vision: ChatCfg | None = None
    egress: EgressCfg = EgressCfg()


def _is_private(base_url: str | None) -> bool:
    if not base_url:
        return False
    host = urlparse(base_url).hostname or ""
    if host in {"localhost", "ollama", "host.docker.internal"}:
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def check_egress(cfg: ModelsConfig) -> None:
    """Refuse to start any adapter that would send data outside, unless the admin allowed it."""
    if cfg.egress.allow_cloud:
        return
    for name, part in (("chat", cfg.chat), ("embed", cfg.embed), ("vision", cfg.vision)):
        if part is None:
            continue
        if part.provider in CLOUD_PROVIDERS or not _is_private(part.base_url):
            raise ProviderError(
                f"egress.allow_cloud is false but {name} uses {part.provider}"
                f" at {part.base_url or 'a public endpoint'}"
            )


@lru_cache
def load_config() -> ModelsConfig:
    with open(get_settings().models_config, encoding="utf-8") as f:
        cfg = ModelsConfig.model_validate(yaml.safe_load(f))
    check_egress(cfg)
    if cfg.embed.dims != get_settings().embed_dims:
        raise ProviderError(
            f"models.yaml embed.dims={cfg.embed.dims} but EMBED_DIMS={get_settings().embed_dims}"
        )
    return cfg


def build_chat(part: ChatCfg) -> ChatModel:
    s = get_settings()
    if part.provider == "openai":
        return OpenAIChat(part.model, s.openai_api_key, part.base_url)
    if part.provider == "anthropic":
        return AnthropicChat(part.model, s.anthropic_api_key)
    return OllamaChat(part.model, part.base_url or "http://ollama:11434")


def get_chat() -> ChatModel:
    return build_chat(load_config().chat)


def get_embedder() -> Embedder:
    e = load_config().embed
    s = get_settings()
    if e.provider == "openai":
        return OpenAIEmbedder(e.model, e.dims, s.openai_api_key, e.base_url)
    return OllamaEmbedder(e.model, e.dims, e.base_url or "http://ollama:11434")


def get_reranker() -> Reranker:
    return LLMReranker(get_chat())
