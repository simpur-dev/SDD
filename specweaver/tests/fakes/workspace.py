from __future__ import annotations

import hashlib

from specweaver.domain.entities import FileChange


class InMemoryWorkspace:
    """Deterministic workspace fake backed by an in-memory file tree."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        ref: str = "deadbeef",
    ) -> None:
        self.files = dict(files or {})
        self._ref = ref

    async def list_files(self) -> list[str]:
        return sorted(self.files)

    async def current_ref(self) -> str:
        return self._ref

    async def changed_files(
        self, base: str, head: str
    ) -> list[FileChange]:
        return []

    async def read_file(self, path: str) -> str:
        return self.files[path]

    async def exists(self, path: str) -> bool:
        return path in self.files

    async def checksum(self, path: str) -> str:
        digest = hashlib.sha256(self.files[path].encode("utf-8")).hexdigest()
        return f"sha256:{digest}"
