from anthropic import Anthropic
from pydantic import BaseModel

from app.providers.base import Message, ProviderError, Response


class AnthropicChat:
    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._client = Anthropic(api_key=api_key)

    def generate(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Response:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        kwargs: dict = {"model": self.model, "max_tokens": 4096, "messages": turns}
        if system:
            kwargs["system"] = system
        if schema is not None:
            # Tool use is how Anthropic returns schema-validated JSON.
            kwargs["tools"] = [
                {
                    "name": "result",
                    "description": "Return the answer in this format.",
                    "input_schema": schema.model_json_schema(),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": "result"}
        r = self._client.messages.create(**kwargs)
        parsed = None
        text = ""
        for block in r.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use" and schema is not None:
                parsed = schema.model_validate(block.input)
                text = parsed.model_dump_json()
        return Response(
            text=text,
            parsed=parsed,
            input_tokens=r.usage.input_tokens,
            output_tokens=r.usage.output_tokens,
        )
