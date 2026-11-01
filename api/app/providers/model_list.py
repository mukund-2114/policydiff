"""Ask a provider which models it offers, so the Settings page can show a list instead of a box.

Typing a model name by hand invites a misspelling that only shows up when a scan fails. Here the
provider is asked and the answer is filtered to what suits the job: chat and figure models, or
embedding models. If the provider cannot be asked (no key, no list endpoint, an unreachable server)
the result says why and the page falls back to the typed field, so nobody is locked out (D55).
"""

import httpx
from anthropic import Anthropic
from anthropic import APIError as AnthropicError
from openai import OpenAI, OpenAIError

# OpenAI's list holds every model it sells. These are the ones that are not chat models.
NOT_CHAT = (
    "embedding",
    "audio",
    "realtime",
    "transcribe",
    "tts",
    "whisper",
    "image",
    "search",
    "moderation",
    "instruct",
    "dall-e",
    "codex",
    "davinci",
    "babbage",
)
CHAT_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")


def keep_openai(model_id: str, job: str) -> bool:
    if job == "embed":
        return model_id.startswith("text-embedding")
    return model_id.startswith(CHAT_PREFIXES) and not any(w in model_id for w in NOT_CHAT)


def _openai_like(key: str, base_url: str | None, job: str) -> list[str]:
    client = OpenAI(api_key=key or "none", base_url=base_url, timeout=15)
    models = sorted(client.models.list(), key=lambda m: m.created or 0, reverse=True)
    ids = [m.id for m in models]
    # A server the admin runs may name its models anything, so only OpenAI's own list is filtered.
    return [i for i in ids if keep_openai(i, job)] if base_url is None else ids


def _anthropic(key: str) -> list[str]:
    page = Anthropic(api_key=key, timeout=15).models.list(limit=100)
    return [m.id for m in page.data]


def _ollama(base_url: str) -> list[str]:
    r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
    r.raise_for_status()
    return sorted(m["name"] for m in r.json().get("models", []))


def list_models(
    provider: str, job: str, key: str = "", base_url: str | None = None
) -> tuple[list[str], str | None]:
    """Returns (model names, a message when the list is empty or unavailable)."""
    try:
        if provider == "openai":
            if not key:
                return [], "Add an OpenAI key to load the list."
            return _openai_like(key, None, job), None
        if provider == "openai_compatible":
            if not base_url:
                return [], "Enter the server address to load its models."
            return _openai_like(key, base_url, job), None
        if provider == "anthropic":
            if job == "embed":
                return [], "Anthropic has no embedding models."
            if not key:
                return [], "Add an Anthropic key to load the list."
            return _anthropic(key), None
        if provider == "ollama":
            return _ollama(base_url or "http://ollama:11434"), None
    except (OpenAIError, AnthropicError, httpx.HTTPError) as e:
        return [], f"Could not load the list ({type(e).__name__}). Type the name instead."
    return [], "This provider has no model list here. Type the model name."
