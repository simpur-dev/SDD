from __future__ import annotations

from fakes.catalog import InMemoryCatalog, InMemoryHybridSearch
from fakes.inference import ScriptedEmbedding

from specweaver.application.engines.assembly import AssemblyEngine
from specweaver.application.engines.retrieval import (
    GraphExpander,
    QueryPlanner,
    RetrievalEngine,
)
from specweaver.application.engines.validity import (
    ConflictDetector,
    GapDetector,
    LifecycleValidator,
    ProvenanceDetector,
    SuspectDetector,
    ValidityEngine,
)
from specweaver.application.usecases.get_context import GetContext
from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import (
    ArtifactType,
    RelationKind,
)
from specweaver.shared.telemetry import Telemetry


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


def _usecase(catalog: InMemoryCatalog) -> GetContext:
    retrieval = RetrievalEngine(
        QueryPlanner(None),
        ScriptedEmbedding(8),
        InMemoryHybridSearch(catalog),
        GraphExpander(catalog, depth=2),
        n_results=10,
    )
    validity = ValidityEngine(
        LifecycleValidator(),
        ConflictDetector(),
        GapDetector(catalog),
        SuspectDetector(catalog),
        ProvenanceDetector(),
    )
    return GetContext(
        retrieval,
        validity,
        AssemblyEngine(8000),
        Telemetry(),
    )


async def test_get_context_returns_bundle_and_markdown() -> None:
    catalog = await _catalog()
    result = await _usecase(catalog).execute(
        "railway", "调整 发车时间"
    )
    assert result.markdown.startswith("# Context")
    cited = {c.artifact_id for c in result.bundle.citations}
    assert {"REQ-1", "CODE-1", "TST-1"} <= cited
    assert result.bundle.task.project_id == "railway"
