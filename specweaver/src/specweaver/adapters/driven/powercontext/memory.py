from __future__ import annotations

from ....domain.ports.memory import MemoryEntry
from ....domain.values import Citation, SourceRef
from ....shared.errors import SWError
from .client import PowerContextClient

_URI_PREFIX = "powercontext://memory/"


def scope_from_uri(uri: str) -> str:
    return uri[len(_URI_PREFIX):]


def pc_to_domain(scope_id: str, pc: dict) -> MemoryEntry:
    citation = pc["citation"]
    entry_id = citation["entry_id"]
    revision = citation["memory_ref"]["revision"]
    return MemoryEntry(
        id=entry_id,
        scope_id=scope_id,
        kind=pc.get("kind", "working_note"),
        content=pc.get("text", ""),
        active=pc.get("state") == "active",
        citation=Citation(
            artifact_id=entry_id,
            version=citation.get("entry_version_id"),
            source=SourceRef(
                uri=f"{_URI_PREFIX}{scope_id}",
                locator=entry_id,
                kind="memory",
                checksum=str(revision),
            ),
        ),
    )


class PowerContextMemory:
    def __init__(self, client: PowerContextClient) -> None:
        self._client = client

    async def resolve_scope(self, project_id: str) -> str:
        return await self._client.ensure_scope(
            f"sw:{project_id}", f"SpecWeaver scope for project {project_id}"
        )

    async def remember(self, entry: MemoryEntry) -> MemoryEntry:
        res = await self._client.post(
            "/v1/memory/remember",
            {
                "scope_id": entry.scope_id,
                "kind": entry.kind,
                "text": entry.content,
            },
        )
        out = pc_to_domain(entry.scope_id, res["entry"])
        out.tags = entry.tags
        return out

    async def search(
        self, scope_id: str, query: str, n: int = 8
    ) -> list[MemoryEntry]:
        res = await self._client.post(
            "/v1/memory/search",
            {
                "scope_id": scope_id,
                "query": query,
                "limit": n,
                "mode": "auto",
            },
        )
        out: list[MemoryEntry] = []
        for hit in res.get("hits", []):
            citation = hit["citation"]
            entry_id = citation["entry_id"]
            out.append(
                MemoryEntry(
                    id=entry_id,
                    scope_id=scope_id,
                    content=hit["text"],
                    citation=Citation(
                        artifact_id=entry_id,
                        version=citation.get("entry_version_id"),
                        source=SourceRef(
                            uri=f"{_URI_PREFIX}{scope_id}",
                            locator=entry_id,
                            kind="memory",
                            checksum=str(citation["memory_ref"]["revision"]),
                        ),
                    ),
                )
            )
        return out

    async def list_entries(
        self, scope_id: str, include_inactive: bool = False
    ) -> list[MemoryEntry]:
        res = await self._client.post(
            "/v1/memory/entries/list",
            {"scope_id": scope_id, "include_inactive": include_inactive},
        )
        return [
            pc_to_domain(scope_id, entry)
            for entry in res.get("entries", [])
        ]

    async def _latest(self, scope_id: str, entry_id: str) -> dict | None:
        res = await self._client.post(
            "/v1/memory/entries/list",
            {"scope_id": scope_id, "include_inactive": True},
        )
        for entry in res.get("entries", []):
            if entry["citation"]["entry_id"] == entry_id:
                return entry
        return None

    async def revise(
        self, citation: Citation, content: str, reason: str = ""
    ) -> MemoryEntry:
        scope_id = scope_from_uri(citation.source.uri)
        entry_id = citation.source.locator or citation.artifact_id
        latest = await self._latest(scope_id, entry_id)
        if latest is None:
            raise SWError(f"memory entry not found: {entry_id}")
        res = await self._client.post(
            "/v1/memory/entries/revise",
            {
                "scope_id": scope_id,
                "citation": latest["citation"],
                "kind": latest.get("kind", "working_note"),
                "text": content,
                "reason": reason or "revised by SpecWeaver",
            },
        )
        return pc_to_domain(scope_id, res["entry"])

    async def retire(self, citation: Citation, reason: str = "") -> None:
        scope_id = scope_from_uri(citation.source.uri)
        entry_id = citation.source.locator or citation.artifact_id
        latest = await self._latest(scope_id, entry_id)
        if latest is None:
            raise SWError(f"memory entry not found: {entry_id}")
        await self._client.post(
            "/v1/memory/entries/retire",
            {
                "scope_id": scope_id,
                "citation": latest["citation"],
                "reason": reason or "retired by SpecWeaver",
            },
        )
