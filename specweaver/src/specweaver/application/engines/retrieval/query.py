from __future__ import annotations

from ....domain.ports.catalog import HybridQuery
from .planner import RetrievalPlan


def build_hybrid_query(
    project_id: str,
    task_text: str,
    plan: RetrievalPlan,
    query_embedding: list[float],
    n_results: int,
) -> HybridQuery:
    text = " ".join(plan.keywords) if plan.keywords else task_text
    return HybridQuery(
        project_id=project_id,
        text=text,
        modules=plan.modules or None,
        types=plan.types or None,
        only_active=False,
        n_results=n_results,
        query_embedding=query_embedding,
    )
