from __future__ import annotations

from pydantic import BaseModel

from ....domain.entities import Artifact, Relation
from ....domain.ports.inference import EmbeddingGatewayPort
from ....domain.ports.workspace import WorkspacePort
from .discovery import FileDiscovery
from .embedding import ArtifactEmbedder
from .graph_mining import mine_relations
from .normalize import to_artifact
from .parsers import ParserRegistry
from .parsers.base import ParsedDocument


class IngestionResult(BaseModel):
    project_id: str
    artifacts: list[Artifact] = []
    relations: list[Relation] = []
    changed_ids: list[str] = []
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


class IngestionEngine:
    """Orchestrates discovery -> parse -> normalize -> graph mining -> embed.

    The engine never writes to backends; it returns artifacts/relations for the
    use case to persist, keeping the pipeline deterministic and unit-testable.
    """

    def __init__(
        self,
        embedding: EmbeddingGatewayPort,
        registry: ParserRegistry | None = None,
        discovery: FileDiscovery | None = None,
    ) -> None:
        self._registry = registry or ParserRegistry()
        self._discovery = discovery or FileDiscovery()
        self._embedder = ArtifactEmbedder(embedding)

    async def run(
        self,
        project_id: str,
        workspace: WorkspacePort,
        existing_checksums: dict[str, str],
    ) -> IngestionResult:
        paths = await workspace.list_files()
        report = self._discovery.discover(paths)

        pairs: list[tuple[ParsedDocument, Artifact]] = []
        changed: list[Artifact] = []
        changed_ids: list[str] = []
        added = updated = unchanged = 0

        for discovered in report.files:
            checksum = await workspace.checksum(discovered.path)
            text = await workspace.read_file(discovered.path)
            parser = self._registry.for_file(discovered.path, discovered.type)
            doc = parser.parse(
                discovered.path, text, checksum, discovered.type
            )
            artifact = to_artifact(project_id, doc)
            previous = existing_checksums.get(artifact.id)
            if previous == checksum:
                unchanged += 1
            else:
                if previous is None:
                    added += 1
                else:
                    updated += 1
                changed.append(artifact)
                changed_ids.append(artifact.id)
            pairs.append((doc, artifact))

        relations = mine_relations(project_id, pairs)
        await self._embedder.embed(changed)

        return IngestionResult(
            project_id=project_id,
            artifacts=[artifact for _, artifact in pairs],
            relations=relations,
            changed_ids=changed_ids,
            added=added,
            updated=updated,
            unchanged=unchanged,
            skipped=len(report.skipped),
        )
