from openai import OpenAI
from pydantic import BaseModel

from app.providers.base import Message, ProviderError, Response


class OpenAIChat:
    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        if not api_key and base_url is None:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.model = model
        self._client = OpenAI(api_key=api_key or "none", base_url=base_url)

    def generate(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Response:
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        if schema is None:
            r = self._client.chat.completions.create(model=self.model, messages=msgs)
            parsed = None
        else:
            r = self._client.beta.chat.completions.parse(
                model=self.model, messages=msgs, response_format=schema
            )
            parsed = r.choices[0].message.parsed
        usage = r.usage
        return Response(
            text=r.choices[0].message.content or "",
            parsed=parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )


class OpenAIEmbedder:
    def __init__(self, model: str, dims: int, api_key: str, base_url: str | None = None):
        if not api_key and base_url is None:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.model = model
        self.dims = dims
        self._client = OpenAI(api_key=api_key or "none", base_url=base_url)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            r = self._client.embeddings.create(model=self.model, input=texts[i : i + 256])
            out.extend(d.embedding for d in r.data)
        if out and len(out[0]) != self.dims:
            raise ProviderError(
                f"Embedding model returned {len(out[0])} dims, config says {self.dims}"
            )
        return out
