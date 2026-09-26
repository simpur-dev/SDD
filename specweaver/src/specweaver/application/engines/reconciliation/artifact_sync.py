from __future__ import annotations

from dataclasses import dataclass, field

from ....domain.entities import Artifact, Relation
from ....domain.enums import LifecycleStatus
from ....domain.ports.inference import EmbeddingGatewayPort
from ....domain.ports.workspace import WorkspacePort
from ..ingestion.embedding import ArtifactEmbedder
from ..ingestion.graph_mining import mine_relations
from ..ingestion.normalize import to_artifact
from ..ingestion.parsers import ParserRegistry
from ..ingestion.parsers.base import ParsedDocument
from ..ingestion.taxonomy import classify_by_path


@dataclass
class SyncOutput:
    rebuilt: list[Artifact]
    superseded: list[Artifact]
    relations: list[Relation] = field(default_factory=list)


class ArtifactSync:
    """Rebuilds changed artifacts, re-mines their edges, applies replacements."""

    def __init__(
        self,
        embedding: EmbeddingGatewayPort,
        registry: ParserRegistry | None = None,
    ) -> None:
        self._registry = registry or ParserRegistry()
        self._embedder = ArtifactEmbedder(embedding)

    @staticmethod
    def _context_doc(artifact: Artifact) -> ParsedDocument:
        """Minimal parsed view of a catalog artifact for edge re-mining."""
        source = artifact.source
        return ParsedDocument(
            path=source.uri if source else artifact.id,
            type=artifact.type,
            title=artifact.title,
            references=list(artifact.based_on),
        )

    async def rebuild(
        self,
        project_id: str,
        workspace: WorkspacePort,
        changed_paths: list[str],
        existing: dict[str, Artifact],
    ) -> SyncOutput:
        rebuilt: list[Artifact] = []
        superseded: list[Artifact] = []
        pairs: list[tuple[ParsedDocument, Artifact]] = []

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
            pairs.append((doc, artifact))

            if artifact.supersedes:
                old = existing.get(artifact.supersedes)
                if old is not None and old.status == LifecycleStatus.active:
                    old.status = LifecycleStatus.superseded
                    old.superseded_by = artifact.id
                    superseded.append(old)

        # Unchanged catalog artifacts join only as edge context: their stored
        # based_on refs re-emit the same deterministic edges (upsert is
        # idempotent), while removed edges are never deleted by this path.
        changed_ids = {artifact.id for artifact in rebuilt}
        for artifact in existing.values():
            if artifact.id in changed_ids:
                continue
            pairs.append((self._context_doc(artifact), artifact))

        await self._embedder.embed(rebuilt)
        return SyncOutput(
            rebuilt=rebuilt,
            superseded=superseded,
            relations=mine_relations(project_id, pairs),
        )
