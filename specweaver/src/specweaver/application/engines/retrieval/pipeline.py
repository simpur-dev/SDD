from __future__ import annotations

from pydantic import BaseModel

from ....domain.ports.catalog import (
    HybridSearchPort,
    ScoredArtifact,
)
from ....domain.ports.inference import EmbeddingGatewayPort
from .graph_expand import GraphExpander
from .planner import QueryPlanner, RetrievalPlan
from .query import build_hybrid_query


class RetrievalResult(BaseModel):
    plan: RetrievalPlan
    scored: list[ScoredArtifact]


def _merge(
    primary: list[ScoredArtifact],
    secondary: list[ScoredArtifact],
    cap: int,
) -> list[ScoredArtifact]:
    best: dict[str, ScoredArtifact] = {}
    for scored in [*primary, *secondary]:
        current = best.get(scored.artifact.id)
        if current is None or scored.score > current.score:
            best[scored.artifact.id] = scored
    ranked = sorted(best.values(), key=lambda s: s.score, reverse=True)
    return ranked[:cap]


class RetrievalEngine:
    """Plan -> embed task -> hybrid search -> graph expand -> merge/rank."""

    def __init__(
        self,
        planner: QueryPlanner,
        embedding: EmbeddingGatewayPort,
        hybrid: HybridSearchPort | None = None,
        expander: GraphExpander | None = None,
        n_results: int = 20,
    ) -> None:
        self._planner = planner
        self._embedding = embedding
        self._hybrid = hybrid
        self._expander = expander
        self._n_results = n_results

    async def run(
        self, project_id: str, task_text: str
    ) -> RetrievalResult:
        plan = await self._planner.plan(task_text)
        query_vectors = await self._embedding.embed([task_text], kind="query")
        query = build_hybrid_query(
            project_id,
            task_text,
            plan,
            query_vectors[0],
            self._n_results,
        )
        primary = (
            await self._hybrid.hybrid_search(query)
            if self._hybrid is not None
            else []
        )
        secondary = (
            await self._expander.expand(primary)
            if self._expander is not None
            else []
        )
        return RetrievalResult(
            plan=plan, scored=_merge(primary, secondary, self._n_results)
        )
