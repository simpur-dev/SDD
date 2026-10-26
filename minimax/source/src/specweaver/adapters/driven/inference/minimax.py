from __future__ import annotations

import httpx

from ....shared.config import InferenceSettings
from ....shared.errors import BackendConnectionError, SWError
from .openai_chat import require_key


class MiniMaxEmbedding:
    """MiniMax embo-01 embeddings (non-standard texts/vectors schema)."""

    dim = 1536

    def __init__(
        self, settings: InferenceSettings, transport=None
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]:
        settings = self._settings
        url = f"{settings.base_url.rstrip('/')}/embeddings"
        body = {
            "model": settings.embed_model,
            "texts": texts,
            "type": kind,
        }
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
        vectors = data.get("vectors")
        if not isinstance(vectors, list):
            raise SWError(
                "embedding endpoint response is missing 'vectors'"
            )
        return vectors
