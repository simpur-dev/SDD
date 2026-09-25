from __future__ import annotations

from dataclasses import dataclass

from ....domain.entities import Artifact
from ....domain.enums import LifecycleStatus
from ....domain.ports.inference import EmbeddingGatewayPort
from ....domain.ports.workspace import WorkspacePort
from ..ingestion.embedding import ArtifactEmbedder
from ..ingestion.normalize import to_artifact
from ..ingestion.parsers import ParserRegistry
from ..ingestion.taxonomy import classify_by_path


@dataclass
class SyncOutput:
    rebuilt: list[Artifact]
    superseded: list[Artifact]


class ArtifactSync:
    """Rebuilds changed artifacts and applies explicit version replacement."""

    def __init__(
        self,
        embedding: EmbeddingGatewayPort,
        registry: ParserRegistry | None = None,
    ) -> None:
        self._registry = registry or ParserRegistry()
        self._embedder = ArtifactEmbedder(embedding)

    async def rebuild(
        self,
        project_id: str,
        workspace: WorkspacePort,
        changed_paths: list[str],
        existing: dict[str, Artifact],
    ) -> SyncOutput:
        rebuilt: list[Artifact] = []
        superseded: list[Artifact] = []

        for path in changed_paths:
            declared = classify_by_path(path)
            if declared is None:
                continue
            checksum = await workspace.checksum(path)
            text = await workspace.read_file(path)
            parser = self._registry.for_file(path, declared)
            doc = parser.parse(path, text, checksum, declared)
            artifact = to_artifact(project_id, doc)
            rebuilt.append(artifact)

            if artifact.supersedes:
                old = existing.get(artifact.supersedes)
                if old is not None and old.status == LifecycleStatus.active:
                    old.status = LifecycleStatus.superseded
                    old.superseded_by = artifact.id
                    superseded.append(old)

        await self._embedder.embed(rebuilt)
        return SyncOutput(rebuilt=rebuilt, superseded=superseded)
