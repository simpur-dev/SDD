from __future__ import annotations

import hashlib
import json

from specweaver.domain.ports.inference import CompletionResult


class ScriptedLLM:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.replies = list(replies or [])
        self.calls: list[str] = []

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        self.calls.append(prompt)
        text = self.replies.pop(0) if self.replies else ""
        structured = None
        if schema and text:
            try:
                structured = json.loads(text)
            except json.JSONDecodeError:
                structured = None
        return CompletionResult(text=text, structured=structured)


class RaisingLLM:
    """LLM whose complete() always fails, to exercise fallback handling."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc or RuntimeError("model unavailable")

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        raise self._exc


class ScriptedEmbedding:
    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    async def embed(
        self, texts: list[str], kind: str = "db"
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            values: list[float] = []
            for j in range(self.dim):
                digest = hashlib.sha256(f"{j}:{text}".encode()).digest()
                values.append(int.from_bytes(digest[:2], "big") / 65535.0)
            out.append(values)
        return out
