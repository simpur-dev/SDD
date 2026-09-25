from __future__ import annotations

import json

import httpx

from ....domain.ports.inference import CompletionResult
from ....domain.values import TokenUsage
from ....shared.config import InferenceSettings
from ....shared.errors import SWError


class MiniMaxLLM:
    def __init__(self, settings: InferenceSettings) -> None:
        self._settings = settings

    def _key(self) -> str:
        if not self._settings.api_key:
            raise SWError("MiniMax api key is not configured")
        return self._settings.api_key.get_secret_value()

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        body: dict = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if schema is not None:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._settings.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self._key()}"},
            )
            resp.raise_for_status()
            data = resp.json()

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


class MiniMaxEmbedding:
    dim = 1536

    def __init__(self, settings: InferenceSettings) -> None:
        self._settings = settings

    def _key(self) -> str:
        if not self._settings.api_key:
            raise SWError("MiniMax api key is not configured")
        return self._settings.api_key.get_secret_value()

    async def _embed(self, texts: list[str], kind: str) -> list[list[float]]:
        body = {
            "model": self._settings.embed_model,
            "texts": texts,
            "type": kind,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._settings.base_url}/embeddings",
                json=body,
                headers={"Authorization": f"Bearer {self._key()}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["vectors"]

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]:
        return await self._embed(texts, kind)
