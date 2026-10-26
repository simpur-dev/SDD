from __future__ import annotations

from pydantic import BaseModel

from ....domain.entities import Artifact, ChangeSet, Relation
from ....domain.ports.inference import EmbeddingGatewayPort
from ....domain.ports.workspace import WorkspacePort
from .artifact_sync import ArtifactSync
from .changes import collect_changes


class ReconciliationResult(BaseModel):
    change_set: ChangeSet
    updated: list[Artifact]
    superseded: list[Artifact]
    relations: list[Relation] = []


class ReconciliationEngine:
    """Collect changes, rebuild artifacts and assemble a change set."""

    def __init__(self, embedding: EmbeddingGatewayPort) -> None:
        self._sync = ArtifactSync(embedding)

    async def run(
        self,
        project_id: str,
        task_id: str,
        workspace: WorkspacePort,
        base_ref: str,
        head_ref: str,
        existing: dict[str, Artifact],
        change_id: str,
    ) -> ReconciliationResult:
        collected = await collect_changes(workspace, base_ref, head_ref)
        active_paths = [
            change.path
            for change in collected.changes
            if change.change_type != "deleted"
        ]
        output = await self._sync.rebuild(
            project_id, workspace, active_paths, existing
        )
        change_set = ChangeSet(
            id=change_id,
            project_id=project_id,
            task_id=task_id,
            files_changed=collected.changes,
            base_checksum=base_ref,
            head_checksum=head_ref,
        )
        return ReconciliationResult(
            change_set=change_set,
            updated=output.rebuilt,
            superseded=output.superseded,
            relations=output.relations,
        )
