"""The three interfaces the pipeline talks to. No vendor SDK is imported outside providers/."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


@dataclass
class Message:
    role: str  # system, user, assistant
    content: str
    images: list[bytes] = field(default_factory=list)  # PNG bytes, for vision models


@dataclass
class Response:
    text: str
    parsed: BaseModel | None
    input_tokens: int
    output_tokens: int


class ChatModel(Protocol):
    def generate(
        self, messages: list[Message], schema: type[BaseModel] | None = None
    ) -> Response: ...


class Embedder(Protocol):
    model: str
    dims: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    def score(self, query: str, docs: list[str]) -> list[float]: ...


class ProviderError(RuntimeError):
    pass


def stream_chat(chat: ChatModel, messages: list[Message]) -> Iterator[tuple[str, object]]:
    """Yields ("text", piece) as the answer is written, then ("usage", tokens) once at the end.

    An adapter that can stream has a `stream` method that does exactly this. One that cannot (a
    local server without streaming, Bedrock here) answers in one call and the whole text arrives
    as a single piece, so the page still works, only without the word-by-word effect.
    """
    if hasattr(chat, "stream"):
        yield from chat.stream(messages)
        return
    r = chat.generate(messages)
    yield "text", r.text
    yield "usage", r.input_tokens + r.output_tokens
