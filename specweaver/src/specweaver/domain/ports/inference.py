from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..values import TokenUsage


class CompletionResult(BaseModel):
    text: str
    structured: dict | None = None
    usage: TokenUsage = TokenUsage()


class LLMGatewayPort(Protocol):
    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult: ...


class EmbeddingGatewayPort(Protocol):
    dim: int

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]: ...
