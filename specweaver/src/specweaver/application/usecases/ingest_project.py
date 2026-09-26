from __future__ import annotations

from pydantic import BaseModel

from ...domain.enums import LifecycleStatus
from ...domain.ports.catalog import ArtifactFilter, CatalogPort
from ...domain.ports.memory import MemoryEntry, MemoryPort
from ...domain.ports.workspace import WorkspacePort
from ...shared.errors import SWError
from ...shared.telemetry import Telemetry
from ..engines.ingestion import IngestionEngine
from .base import UseCase


class IngestProjectRequest(BaseModel):
    project_id: str
    scope_id: str = ""
    register_source: bool = True


class IngestProjectReport(BaseModel):
    project_id: str
    added: int
    updated: int
    unchanged: int
    skipped: int
    relations: int
    changed_ids: list[str]
    source_registered: bool = False
    duplicate_ids: list[str] = []
    deprecated: int = 0


class IngestProject(UseCase):
    """Run the ingestion pipeline, persist results, and register a Source."""

    name = "ingest_project"

    def __init__(
        self,
        engine: IngestionEngine,
        catalog: CatalogPort,
        workspace: WorkspacePort,
        telemetry: Telemetry,
        memory: MemoryPort | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._engine = engine
        self._catalog = catalog
        self._workspace = workspace
        self._memory = memory

    async def __call__(
        self, request: IngestProjectRequest
    ) -> IngestProjectReport:
        with self.span():
            if self._catalog is None:
                raise SWError(
                    "ingest_project needs a working seekdb catalog; "
                    "run `specweaver doctor`"
                )
            existing_artifacts = await self._catalog.list_artifacts(
                ArtifactFilter(project_id=request.project_id)
            )
            existing = {
                a.id: a.checksum
                for a in existing_artifacts
                if a.checksum
            }
            result = await self._engine.run(
                request.project_id, self._workspace, existing
            )

            changed = set(result.changed_ids)
            for artifact in result.artifacts:
                if artifact.id in changed:
                    await self._catalog.upsert_artifact(artifact)
            for relation in result.relations:
                await self._catalog.upsert_relation(relation)

            # audit C5: artifacts whose source file left the workspace are
            # tombstoned (deprecated) instead of lingering as silent stale rows
            current_files = set(await self._workspace.list_files())
            deprecated = 0
            for artifact in existing_artifacts:
                uri = artifact.source.uri if artifact.source else None
                if (
                    not uri
                    or uri in current_files
                    or artifact.id in changed
                    or artifact.status
                    in (
                        LifecycleStatus.deprecated,
                        LifecycleStatus.superseded,
                    )
                ):
                    continue
                await self._catalog.upsert_artifact(
                    artifact.model_copy(
                        update={"status": LifecycleStatus.deprecated}
                    )
                )
                deprecated += 1

            registered = False
            if (
                request.register_source
                and self._memory is not None
                and request.scope_id
            ):
                git_ref = await self._workspace.current_ref()
                content = (
                    f"Ingested project at {git_ref}: +{result.added} "
                    f"~{result.updated} ={result.unchanged} files, "
                    f"{len(result.relations)} relations"
                )
                await self._memory.remember(
                    MemoryEntry(
                        scope_id=request.scope_id,
                        kind="ingestion",
                        content=content,
                        tags=["ingestion", request.project_id],
                    )
                )
                registered = True

            return IngestProjectReport(
                project_id=request.project_id,
                added=result.added,
                updated=result.updated,
                unchanged=result.unchanged,
                skipped=result.skipped,
                relations=len(result.relations),
                changed_ids=result.changed_ids,
                source_registered=registered,
                duplicate_ids=result.duplicate_ids,
                deprecated=deprecated,
            )
