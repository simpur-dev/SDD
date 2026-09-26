from __future__ import annotations

import math

from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import LifecycleStatus
from specweaver.domain.ports.catalog import (
    ArtifactFilter,
    HybridQuery,
    ScoredArtifact,
)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class InMemoryCatalog:
    def __init__(self) -> None:
        self.artifacts: dict[tuple[str, str], Artifact] = {}
        self.relations: list[Relation] = []

    async def upsert_artifact(self, artifact: Artifact) -> None:
        self.artifacts[(artifact.project_id, artifact.id)] = artifact

    async def get_artifact(
        self, project_id: str, artifact_id: str
    ) -> Artifact | None:
        return self.artifacts.get((project_id, artifact_id))

    async def list_artifacts(
        self, flt: ArtifactFilter
    ) -> list[Artifact]:
        out: list[Artifact] = []
        for artifact in self.artifacts.values():
            if artifact.project_id != flt.project_id:
                continue
            if flt.types and artifact.type not in flt.types:
                continue
            if flt.modules and artifact.module not in flt.modules:
                continue
            if flt.status and artifact.status != flt.status:
                continue
            if (
                flt.ref
                and artifact.applies_to_ref
                and flt.ref not in artifact.applies_to_ref
            ):
                continue
            out.append(artifact)
        return out

    async def upsert_relation(self, relation: Relation) -> None:
        self.relations = [
            r
            for r in self.relations
            if not (
                r.project_id == relation.project_id
                and r.src == relation.src
                and r.dst == relation.dst
                and r.kind == relation.kind
            )
        ]
        self.relations.append(relation)

    async def neighbors(
        self,
        project_id: str,
        artifact_id: str,
        kinds,
        depth: int = 1,
    ) -> list[Artifact]:
        visited = {artifact_id}
        frontier = [artifact_id]
        found: set[str] = set()
        for _ in range(depth):
            new: set[str] = set()
            for relation in self.relations:
                if relation.project_id != project_id:
                    continue
                if relation.kind not in kinds:
                    continue
                peer: str | None = None
                if relation.src in frontier:
                    peer = relation.dst
                elif relation.dst in frontier:
                    peer = relation.src
                if peer and peer not in visited:
                    new.add(peer)
            visited |= new
            found |= new
            frontier = list(new)
        return [
            self.artifacts[(project_id, peer_id)]
            for peer_id in found
            if (project_id, peer_id) in self.artifacts
        ]


class InMemoryHybridSearch:
    def __init__(self, catalog: InMemoryCatalog) -> None:
        self._catalog = catalog

    async def hybrid_search(
        self, query: HybridQuery
    ) -> list[ScoredArtifact]:
        terms = query.text.lower().split()
        scored: list[ScoredArtifact] = []
        for artifact in self._catalog.artifacts.values():
            if artifact.project_id != query.project_id:
                continue
            if query.types and artifact.type not in query.types:
                continue
            if query.modules and artifact.module not in query.modules:
                continue
            if (
                query.only_active
                and artifact.status != LifecycleStatus.active
            ):
                continue
            text = artifact.content.lower()
            keyword = sum(1 for term in terms if term in text)
            semantic = 0.0
            if query.query_embedding and artifact.embedding:
                semantic = cosine(query.query_embedding, artifact.embedding)
            score = float(keyword) + semantic
            if score > 0:
                scored.append(
                    ScoredArtifact(artifact=artifact, score=score)
                )
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: query.n_results]
