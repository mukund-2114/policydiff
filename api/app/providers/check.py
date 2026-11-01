"""Check that a provider key works, before it is saved. One cheap call, no clause text is sent.

Returns (ok, message). The message never contains the key.
"""

import httpx
from anthropic import Anthropic
from anthropic import APIError as AnthropicError
from openai import OpenAI, OpenAIError


def check_key(provider: str, key: str) -> tuple[bool, str]:
    try:
        if provider == "openai":
            OpenAI(api_key=key, timeout=15).models.list()
        elif provider == "anthropic":
            Anthropic(api_key=key, timeout=15).models.list(limit=1)
        elif provider == "cohere":
            r = httpx.post(
                "https://api.cohere.com/v1/check-api-key",
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
            if r.status_code != 200 or not r.json().get("valid"):
                return False, "Cohere did not accept this key."
        else:
            return False, f"No check exists for {provider}."
    except (OpenAIError, AnthropicError, httpx.HTTPError) as e:
        return False, f"{provider} did not accept this key ({type(e).__name__})."
    return True, f"{provider} accepted this key."
