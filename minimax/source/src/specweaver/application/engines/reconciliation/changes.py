from __future__ import annotations

from dataclasses import dataclass

from ....domain.entities import FileChange
from ....domain.ports.workspace import WorkspacePort


@dataclass
class CollectedChanges:
    changes: list[FileChange]
    checksums: dict[str, str]


async def collect_changes(
    workspace: WorkspacePort, base: str, head: str
) -> CollectedChanges:
    changes = await workspace.changed_files(base, head)
    checksums: dict[str, str] = {}
    for change in changes:
        if change.change_type == "deleted":
            continue
        if await workspace.exists(change.path):
            checksums[change.path] = await workspace.checksum(change.path)
    return CollectedChanges(changes=changes, checksums=checksums)
