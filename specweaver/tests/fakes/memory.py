from __future__ import annotations

from specweaver.domain.ports.memory import MemoryEntry
from specweaver.domain.values import Citation, SourceRef


class InMemoryMemory:
    def __init__(self) -> None:
        self.entries: list[MemoryEntry] = []

    async def resolve_scope(self, project_id: str) -> str:
        return f"scp-{project_id}"

    async def remember(self, entry: MemoryEntry) -> MemoryEntry:
        eid = f"mem-{len(self.entries) + 1}"
        stored = entry.model_copy(
            update={
                "id": eid,
                "active": True,
                "citation": entry.citation
                or Citation(
                    artifact_id=eid,
                    source=SourceRef(
                        uri=f"powercontext://memory/{entry.scope_id}",
                        locator=eid,
                    ),
                ),
            }
        )
        self.entries.append(stored)
        return stored

    async def search(
        self, scope_id: str, query: str, n: int = 8
    ) -> list[MemoryEntry]:
        terms = query.lower().split()
        hits = [
            entry
            for entry in self.entries
            if entry.scope_id == scope_id
            and entry.active
            and any(term in entry.content.lower() for term in terms)
        ]
        return hits[:n]

    async def list_entries(
        self, scope_id: str, include_inactive: bool = False
    ) -> list[MemoryEntry]:
        return [
            entry
            for entry in self.entries
            if entry.scope_id == scope_id
            and (include_inactive or entry.active)
        ]

    async def revise(
        self, citation: Citation, content: str, reason: str = ""
    ) -> MemoryEntry:
        for i, entry in enumerate(self.entries):
            if entry.id == citation.artifact_id:
                revised = entry.model_copy(update={"content": content})
                self.entries[i] = revised
                return revised
        raise KeyError(citation.artifact_id)

    async def retire(self, citation: Citation, reason: str = "") -> None:
        for i, entry in enumerate(self.entries):
            if entry.id == citation.artifact_id:
                self.entries[i] = entry.model_copy(update={"active": False})
                return
        raise KeyError(citation.artifact_id)
