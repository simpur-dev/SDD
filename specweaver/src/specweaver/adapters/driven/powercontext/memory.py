from __future__ import annotations

from ....domain.ports.memory import MemoryEntry
from ....domain.values import Citation, SourceRef
from ....shared.errors import SWError
from .client import PowerContextClient, require

_URI_PREFIX = "powercontext://memory/"


def scope_from_uri(uri: str) -> str:
    return uri[len(_URI_PREFIX):]


def pc_to_domain(scope_id: str, pc: dict) -> MemoryEntry:
    citation = require(pc, "citation", "memory entry")
    entry_id = require(citation, "entry_id", "memory citation")
    memory_ref = require(citation, "memory_ref", "memory citation")
    revision = require(memory_ref, "revision", "memory reference")
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
        raw = res.get("entry")
        if raw is None:
            # measured 2026-09-27: PowerContext de-duplicates identical text
            # inside one memory and answers 200 with entry=null. The fact is
            # stored either way, so report the existing entry (remember stays
            # idempotent) instead of failing a re-run of the same task.
            raw = await self._by_text(entry.scope_id, entry.content)
            if raw is None:
                raise SWError(
                    "powercontext memory remember returned neither a new nor "
                    f"an existing entry for {entry.content[:60]!r}"
                )
        out = pc_to_domain(entry.scope_id, raw)
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
            citation = require(hit, "citation", "memory search hit")
            entry_id = require(citation, "entry_id", "memory citation")
            memory_ref = require(citation, "memory_ref", "memory citation")
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
                            checksum=str(
                            require(
                                memory_ref, "revision", "memory reference"
                            )
                        ),
                        ),
                    ),
                )
            )
        return out

    async def list_entries(
        self, scope_id: str, include_inactive: bool = False
    ) -> list[MemoryEntry]:
        return [
            pc_to_domain(scope_id, entry)
            for entry in await self._list_raw(scope_id, include_inactive)
        ]

    async def _list_raw(
        self, scope_id: str, include_inactive: bool = True
    ) -> list[dict]:
        res = await self._client.post(
            "/v1/memory/entries/list",
            {"scope_id": scope_id, "include_inactive": include_inactive},
        )
        return list(res.get("entries", []))

    async def _latest(self, scope_id: str, entry_id: str) -> dict | None:
        for entry in await self._list_raw(scope_id):
            citation = entry.get("citation") or {}
            if citation.get("entry_id") == entry_id:
                return entry
        return None

    async def _by_text(self, scope_id: str, text: str) -> dict | None:
        for entry in await self._list_raw(scope_id):
            if entry.get("text") == text:
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
        return pc_to_domain(
            scope_id, require(res, "entry", "memory revise response")
        )

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
