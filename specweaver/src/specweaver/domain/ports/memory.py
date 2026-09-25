from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..values import Citation


class MemoryEntry(BaseModel):
    id: str | None = None
    scope_id: str
    kind: str = "working_note"
    content: str
    tags: list[str] = []
    citation: Citation | None = None
    active: bool = True


class MemoryPort(Protocol):
    async def remember(self, entry: MemoryEntry) -> MemoryEntry: ...

    async def search(
        self, scope_id: str, query: str, n: int = 8
    ) -> list[MemoryEntry]: ...

    async def list_entries(
        self, scope_id: str, include_inactive: bool = False
    ) -> list[MemoryEntry]: ...

    async def revise(
        self, citation: Citation, content: str, reason: str = ""
    ) -> MemoryEntry: ...

    async def retire(self, citation: Citation, reason: str = "") -> None: ...
