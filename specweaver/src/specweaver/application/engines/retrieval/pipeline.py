from __future__ import annotations

from pydantic import BaseModel

from ....domain.enums import LifecycleStatus
from ....domain.ports.catalog import (
    ArtifactFilter,
    CatalogPort,
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
        catalog: CatalogPort | None = None,
    ) -> None:
        self._planner = planner
        self._embedding = embedding
        self._hybrid = hybrid
        self._expander = expander
        self._n_results = n_results
        self._catalog = catalog

    async def run(
        self, project_id: str, task_text: str
    ) -> RetrievalResult:
        if not task_text.strip():
            # Degenerate query: an empty task must not reach the backend
            # (pyseekdb rejects empty $contains with OperationalError 1210).
            return RetrievalResult(
                plan=RetrievalPlan(objective=task_text), scored=[]
            )
        known_modules: list[str] | None = None
        if self._catalog is not None:
            artifacts = await self._catalog.list_artifacts(
                ArtifactFilter(
                    project_id=project_id,
                    status=LifecycleStatus.active,
                )
            )
            known_modules = sorted(
                {a.module for a in artifacts if a.module}
            )
        plan = await self._planner.plan(task_text, known_modules)
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
        if not primary and (query.modules or query.types):
            # narrowing excluded everything: relax once and retry
            query = query.model_copy(
                update={"modules": None, "types": None}
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
