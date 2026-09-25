from __future__ import annotations

from fakes.catalog import InMemoryCatalog, InMemoryHybridSearch
from fakes.inference import ScriptedEmbedding

from specweaver.application.engines.retrieval import (
    GraphExpander,
    QueryPlanner,
    RetrievalEngine,
)
from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import (
    ArtifactType,
    RelationKind,
)


async def _catalog() -> InMemoryCatalog:
    catalog = InMemoryCatalog()
    req = Artifact(
        id="REQ-1",
        project_id="railway",
        type=ArtifactType.requirement,
        title="按站调整发车时间",
        content="# 需求\n- 应能调整发车时间",
    )
    code = Artifact(
        id="CODE-1",
        project_id="railway",
        type=ArtifactType.code,
        title="schedule",
        content="def adjust_departure():\n    return True\n",
    )
    test = Artifact(
        id="TST-1",
        project_id="railway",
        type=ArtifactType.test,
        title="test_schedule",
        content="def test_adjust_departure():\n    assert True\n",
    )
    for artifact in (req, code, test):
        await catalog.upsert_artifact(artifact)
    await catalog.upsert_relation(
        Relation(
            project_id="railway",
            src=code.id,
            dst=req.id,
            kind=RelationKind.realizes,
        )
    )
    await catalog.upsert_relation(
        Relation(
            project_id="railway",
            src=test.id,
            dst=code.id,
            kind=RelationKind.tests,
        )
    )
    return catalog


def _engine(catalog: InMemoryCatalog) -> RetrievalEngine:
    return RetrievalEngine(
        QueryPlanner(None),
        ScriptedEmbedding(dim=8),
        InMemoryHybridSearch(catalog),
        GraphExpander(catalog, depth=2),
        n_results=10,
    )


async def test_retrieval_finds_requirement_and_completes_chain() -> None:
    catalog = await _catalog()
    result = await _engine(catalog).run("railway", "调整 发车时间")

    ids = {s.artifact.id for s in result.scored}
    assert "REQ-1" in ids
    assert "CODE-1" in ids
    assert "TST-1" in ids
    ranked = [s.artifact.id for s in result.scored]
    assert ranked[0] == "REQ-1"
