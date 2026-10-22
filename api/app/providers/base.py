"""The three interfaces the pipeline talks to. No vendor SDK is imported outside providers/."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class Message:
    role: str  # system, user, assistant
    content: str


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
