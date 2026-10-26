from __future__ import annotations

import hashlib

from ....domain.ports.inference import CompletionResult
from ....shared.errors import InferenceUnavailable


class NullLLM:
    """Fallback when no LLM is configured: callers degrade to rule-based paths."""

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        raise InferenceUnavailable("no LLM provider configured")


class DeterministicEmbedding:
    """Repeatable hash-based pseudo-vectors so the pipeline runs without a key.

    Not semantically meaningful; replace with MiniMaxEmbedding for real search.
    """

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        values: list[float] = []
        for j in range(self.dim):
            digest = hashlib.sha256(f"{j}:{text}".encode()).digest()
            values.append(int.from_bytes(digest[:2], "big") / 65535.0)
        return values

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]:
        return [self._vector(text) for text in texts]
