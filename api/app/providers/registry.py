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
from app.providers.cohere_rerank import CohereReranker
from app.providers.local_rerank import LocalReranker
from app.providers.ollama_adapter import OllamaChat, OllamaEmbedder
from app.providers.openai_adapter import OpenAIChat, OpenAIEmbedder
from app.providers.rerank import LLMReranker
from app.services import runtime

CLOUD_PROVIDERS = {"openai", "anthropic", "cohere"}


DEFAULT_LOCAL_RERANKER = "Xenova/ms-marco-MiniLM-L-6-v2"  # about 80 MB


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
    provider: Literal["llm", "local", "cohere"] = "llm"
    model: str | None = None  # local and cohere only; each has a default


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
    if cfg.rerank.provider == "cohere":  # the other rerankers run here or use the chat model
        raise ProviderError("egress.allow_cloud is false but rerank uses cohere")


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


def effective_config(override: dict | None = None) -> ModelsConfig:
    """models.yaml with the Settings page choices laid on top. `override` tries choices unsaved."""
    cfg = load_config().model_copy(deep=True)
    data = runtime.stored_data() if override is None else override
    for name in ("chat", "vision"):
        if pick := data.get(name):
            current = getattr(cfg, name)
            same = current is not None and current.provider == pick["provider"]
            base_url = current.base_url if same else None
            setattr(cfg, name, ChatCfg(base_url=base_url, **pick))
    if pick := data.get("rerank"):
        cfg.rerank = RerankCfg(**pick)
    check_egress(cfg)
    return cfg


def build_chat(part: ChatCfg) -> ChatModel:
    if part.provider == "openai":
        return OpenAIChat(part.model, runtime.secret("openai"), part.base_url)
    if part.provider == "anthropic":
        return AnthropicChat(part.model, runtime.secret("anthropic"))
    return OllamaChat(part.model, part.base_url or "http://ollama:11434")


def get_chat(cfg: ModelsConfig | None = None) -> ChatModel:
    return build_chat((cfg or effective_config()).chat)


def get_vision(cfg: ModelsConfig | None = None) -> ChatModel:
    """The model that reads figures. `vision:` if set, otherwise the chat model."""
    cfg = cfg or effective_config()
    return build_chat(cfg.vision or cfg.chat)


def get_embedder() -> Embedder:
    e = load_config().embed  # the embedding model is not on the Settings page (D49)
    if e.provider == "openai":
        return OpenAIEmbedder(e.model, e.dims, runtime.secret("openai"), e.base_url)
    return OllamaEmbedder(e.model, e.dims, e.base_url or "http://ollama:11434")


def get_reranker(cfg: ModelsConfig | None = None) -> Reranker:
    cfg, s = cfg or effective_config(), get_settings()
    r = cfg.rerank
    if r.provider == "local":
        return LocalReranker(r.model or DEFAULT_LOCAL_RERANKER, s.model_cache_dir or None)
    if r.provider == "cohere":
        return CohereReranker(r.model or "rerank-v3.5", runtime.secret("cohere"))
    return LLMReranker(get_chat(cfg))
