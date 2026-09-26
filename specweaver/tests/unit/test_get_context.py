from __future__ import annotations

from fakes.activity import InMemoryActivityLog
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
from specweaver.application.usecases.get_context import (
    GetContext,
    GetContextRequest,
)
from specweaver.domain.entities import Artifact, Relation, TestRun
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


def _usecase(
    catalog: InMemoryCatalog, activity=None
) -> GetContext:
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
        activity=activity,
    )


async def test_get_context_returns_bundle_and_markdown() -> None:
    catalog = await _catalog()
    result = await _usecase(catalog)(
        GetContextRequest(project_id="railway", task_text="调整 发车时间")
    )
    assert result.markdown.startswith("# Context")
    cited = {c.artifact_id for c in result.bundle.citations}
    assert {"REQ-1", "CODE-1", "TST-1"} <= cited
    assert result.bundle.task.project_id == "railway"
    assert result.bundle.last_test_run is None


async def test_get_context_includes_latest_test_run() -> None:
    catalog = await _catalog()
    activity = InMemoryActivityLog()
    await activity.record_test_run(
        TestRun(
            id="tr-old", project_id="railway", task_id="task-1",
            total=3, passed=2, failed=1,
        )
    )
    await activity.record_test_run(
        TestRun(
            id="tr-new", project_id="railway", task_id="task-1",
            command="pytest", total=3, passed=3, failed=0,
            commit_ref="head9",
        )
    )

    result = await _usecase(catalog, activity=activity)(
        GetContextRequest(project_id="railway", task_text="调整 发车时间")
    )

    assert result.bundle.last_test_run is not None
    assert result.bundle.last_test_run.id == "tr-new"
    assert "last test run [PASS]" in result.markdown
    assert "ref=head9" in result.markdown
    assert result.bundle.budget is not None
    assert result.bundle.budget.used_bytes <= 8000
