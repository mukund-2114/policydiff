import base64
from collections.abc import Iterator

from openai import BadRequestError, OpenAI
from pydantic import BaseModel

from app.providers.base import Message, ProviderError, Response


def _content(m: Message):
    """Plain text, or text plus images in the shape the vision models expect."""
    if not m.images:
        return m.content
    parts = [{"type": "text", "text": m.content}]
    for png in m.images:
        url = "data:image/png;base64," + base64.b64encode(png).decode()
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


class OpenAIChat:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        reasoning_effort: str | None = None,
    ):
        if not api_key and base_url is None:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.model = model
        self._client = OpenAI(api_key=api_key or "none", base_url=base_url)
        # Reasoning models think before they answer, which can add many seconds. A chat that
        # needs the first word quickly asks for little thinking. A model that does not take the
        # setting refuses it once, and then it is left out.
        self._effort = reasoning_effort

    def _call(self, create, **kwargs):
        if self._effort:
            try:
                return create(reasoning_effort=self._effort, **kwargs)
            except BadRequestError:
                self._effort = None
        return create(**kwargs)

    def generate(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Response:
        msgs = [{"role": m.role, "content": _content(m)} for m in messages]
        if schema is None:
            r = self._call(self._client.chat.completions.create, model=self.model, messages=msgs)
            parsed = None
        else:
            r = self._call(
                self._client.beta.chat.completions.parse,
                model=self.model,
                messages=msgs,
                response_format=schema,
            )
            parsed = r.choices[0].message.parsed
        usage = r.usage
        return Response(
            text=r.choices[0].message.content or "",
            parsed=parsed,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def stream(self, messages: list[Message]) -> Iterator[tuple[str, object]]:
        """Pieces of the answer as they are written, then the token count."""
        msgs = [{"role": m.role, "content": _content(m)} for m in messages]
        events = self._call(
            self._client.chat.completions.create,
            model=self.model,
            messages=msgs,
            stream=True,
            stream_options={"include_usage": True},
        )
        tokens = 0
        for event in events:
            if event.usage:
                tokens = event.usage.prompt_tokens + event.usage.completion_tokens
            if event.choices and event.choices[0].delta.content:
                yield "text", event.choices[0].delta.content
        yield "usage", tokens


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
