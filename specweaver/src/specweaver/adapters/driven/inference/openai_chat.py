"""OpenAI-compatible chat-completions adapter (works with MiniMax and DeepSeek).

Embedding endpoints are NOT covered here: MiniMax uses a non-standard
texts/vectors schema (see minimax.MiniMaxEmbedding) and DeepSeek exposes no
embeddings API at all (docs/02 §7.3 measured 404).
"""
from __future__ import annotations

import json

import httpx

from ....domain.ports.inference import CompletionResult
from ....domain.values import TokenUsage
from ....shared.config import InferenceSettings
from ....shared.errors import BackendConnectionError, SWError


def require_key(settings: InferenceSettings) -> str:
    if not settings.api_key:
        raise SWError(
            f"provider={settings.provider} requires INFERENCE__API_KEY "
            "to be configured"
        )
    return settings.api_key.get_secret_value()


async def post_chat(
    settings: InferenceSettings, body: dict, transport=None
) -> dict:
    """POST {base_url}/chat/completions with the shared error contract."""
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(
            timeout=60.0, transport=transport
        ) as client:
            resp = await client.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {require_key(settings)}"
                },
            )
    except httpx.RequestError as exc:
        raise BackendConnectionError(
            f"inference provider unreachable at {url}: {exc}"
        ) from exc
    if resp.status_code >= 400:
        raise SWError(
            f"inference provider {resp.status_code} on {url}: "
            f"{resp.text[:200]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise SWError(
            f"inference provider returned a non-JSON body: "
            f"{resp.text[:200]}"
        ) from exc


class OpenAIChatLLM:
    """Provider-agnostic chat adapter: base_url/model come from settings."""

    def __init__(self, settings: InferenceSettings, transport=None) -> None:
        self._settings = settings
        self._transport = transport

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        body: dict = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            body["response_format"] = {"type": "json_object"}
        data = await post_chat(self._settings, body, self._transport)

        message = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        structured = None
        if schema is not None:
            try:
                structured = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                structured = None
        return CompletionResult(
            text=message,
            structured=structured,
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            ),
        )
