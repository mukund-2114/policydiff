"""Optional offline adapter. Not needed for the default install."""

import httpx
from pydantic import BaseModel

from app.providers.base import Message, ProviderError, Response


class OllamaChat:
    def __init__(self, model: str, base_url: str):
        self.model = model
        self._base = base_url.rstrip("/")

    def generate(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Response:
        body: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": 0},
        }
        if schema is not None:
            body["format"] = schema.model_json_schema()
        r = httpx.post(f"{self._base}/api/chat", json=body, timeout=300)
        if r.status_code != 200:
            raise ProviderError(f"Ollama returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        text = data["message"]["content"]
        return Response(
            text=text,
            parsed=schema.model_validate_json(text) if schema else None,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
        )


class OllamaEmbedder:
    def __init__(self, model: str, dims: int, base_url: str):
        self.model = model
        self.dims = dims
        self._base = base_url.rstrip("/")

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = httpx.post(
            f"{self._base}/api/embed", json={"model": self.model, "input": texts}, timeout=300
        )
        if r.status_code != 200:
            raise ProviderError(f"Ollama returned {r.status_code}: {r.text[:200]}")
        return r.json()["embeddings"]
