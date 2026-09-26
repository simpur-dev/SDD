"""Standard OpenAI-compatible /embeddings adapter (Qianwen gateway etc.)."""
from __future__ import annotations

import httpx

from ....shared.config import InferenceSettings
from ....shared.errors import BackendConnectionError, SWError
from .openai_chat import require_key


class OpenAIEmbedding:
    """POST {base_url}/embeddings with {model, input} -> data[].embedding."""

    def __init__(
        self, settings: InferenceSettings, transport=None
    ) -> None:
        self._settings = settings
        self._transport = transport
        self.dim = settings.dim

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]:
        settings = self._settings
        url = f"{settings.base_url.rstrip('/')}/embeddings"
        body = {"model": settings.embed_model, "input": texts}
        try:
            async with httpx.AsyncClient(
                timeout=60.0, transport=self._transport
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
                f"embedding endpoint unreachable at {url}: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise SWError(
                f"embedding endpoint {resp.status_code} on {url}: "
                f"{resp.text[:200]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise SWError(
                "embedding endpoint returned a non-JSON body: "
                f"{resp.text[:200]}"
            ) from exc
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise SWError(
                "embedding endpoint response is missing 'data' entries"
            )
        vectors = [item["embedding"] for item in items]
        if any(len(v) != self.dim for v in vectors):
            raise SWError(
                "embedding dimension mismatch: configured "
                f"INFERENCE__DIM={self.dim}, provider returned "
                f"{sorted({len(v) for v in vectors})}"
            )
        return vectors
