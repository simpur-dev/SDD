from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..entities import Artifact, Relation
from ..enums import ArtifactType, LifecycleStatus, RelationKind


class ArtifactFilter(BaseModel):
    project_id: str
    types: list[ArtifactType] | None = None
    modules: list[str] | None = None
    status: LifecycleStatus | None = None
    ref: str | None = None


class HybridQuery(BaseModel):
    project_id: str
    text: str
    modules: list[str] | None = None
    types: list[ArtifactType] | None = None
    only_active: bool = True
    ref: str | None = None
    n_results: int = 20
    use_keyword: bool = True
    use_semantic: bool = True
    query_embedding: list[float] | None = None


class ScoredArtifact(BaseModel):
    artifact: Artifact
    score: float = 0.0
    keyword_score: float | None = None
    semantic_score: float | None = None


class CatalogPort(Protocol):
    """Project-scoped catalog: artifact ids collide across projects (e.g.
    REQ-1), so every single-artifact access must carry its project_id."""

    async def upsert_artifact(self, artifact: Artifact) -> None: ...

    async def get_artifact(
        self, project_id: str, artifact_id: str
    ) -> Artifact | None: ...

    async def list_artifacts(self, filter: ArtifactFilter) -> list[Artifact]: ...

    async def upsert_relation(self, relation: Relation) -> None: ...

    async def neighbors(
        self,
        project_id: str,
        artifact_id: str,
        kinds: list[RelationKind],
        depth: int = 1,
    ) -> list[Artifact]: ...


class HybridSearchPort(Protocol):
    async def hybrid_search(self, query: HybridQuery) -> list[ScoredArtifact]: ...
