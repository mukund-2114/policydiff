"""Amazon Bedrock chat through the Converse API: Claude, Llama, Nova and others behind one call.

No key is stored. boto3 finds credentials the usual AWS way (an IAM role on the machine, or the
AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY variables), and the region comes from AWS_REGION.
A schema is returned through a forced tool call, the same way the Anthropic adapter does it.
"""

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel

from app.providers.base import Message, ProviderError, Response


def _blocks(m: Message) -> list[dict]:
    blocks = [{"text": m.content}]
    blocks += [{"image": {"format": "png", "source": {"bytes": png}}} for png in m.images]
    return blocks


class BedrockChat:
    def __init__(self, model: str, region: str = "", client=None):
        self.model = model
        self._client = client or boto3.client("bedrock-runtime", region_name=region or None)

    def generate(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Response:
        kwargs: dict = {
            "modelId": self.model,
            "messages": [
                {"role": m.role, "content": _blocks(m)} for m in messages if m.role != "system"
            ],
            "inferenceConfig": {"maxTokens": 4096},
        }
        system = [{"text": m.content} for m in messages if m.role == "system"]
        if system:
            kwargs["system"] = system
        if schema is not None:
            kwargs["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": "result",
                            "description": "Return the answer in this format.",
                            "inputSchema": {"json": schema.model_json_schema()},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": "result"}},
            }
        try:
            r = self._client.converse(**kwargs)
        except (BotoCoreError, ClientError) as e:
            raise ProviderError(f"Bedrock call failed ({type(e).__name__})") from e
        text, parsed = "", None
        for block in r["output"]["message"]["content"]:
            if "text" in block:
                text += block["text"]
            elif "toolUse" in block and schema is not None:
                parsed = schema.model_validate(block["toolUse"]["input"])
                text = parsed.model_dump_json()
        usage = r.get("usage", {})
        return Response(
            text=text,
            parsed=parsed,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )
