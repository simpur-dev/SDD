from __future__ import annotations

from ....domain.enums import RelationKind
from ....domain.ports.catalog import CatalogPort, ScoredArtifact

EXPAND_KINDS = [
    RelationKind.realizes,
    RelationKind.tests,
    RelationKind.covers,
    RelationKind.depends_on,
    RelationKind.refines,
]


class GraphExpander:
    """Completes the traceability chain by walking relations from seed hits."""

    def __init__(
        self,
        catalog: CatalogPort | None = None,
        depth: int = 1,
        attenuation: float = 0.5,
    ) -> None:
        self._catalog = catalog
        self._depth = depth
        self._attenuation = attenuation

    async def expand(
        self, seeds: list[ScoredArtifact]
    ) -> list[ScoredArtifact]:
        if self._catalog is None:
            return []
        extra: dict[str, ScoredArtifact] = {}
        for seed in seeds:
            peers = await self._catalog.neighbors(
                seed.artifact.project_id,
                seed.artifact.id,
                EXPAND_KINDS,
                self._depth,
            )
            for peer in peers:
                candidate = ScoredArtifact(
                    artifact=peer,
                    score=round(seed.score * self._attenuation, 4),
                )
                current = extra.get(peer.id)
                if current is None or candidate.score > current.score:
                    extra[peer.id] = candidate
        return list(extra.values())
