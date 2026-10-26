from __future__ import annotations

from fakes.activity import InMemoryActivityLog
from fakes.catalog import InMemoryCatalog, InMemoryHybridSearch
from fakes.inference import ScriptedEmbedding
from fakes.memory import InMemoryMemory

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
from specweaver.domain.ports.memory import MemoryEntry
from specweaver.shared.errors import SWError
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
    catalog, activity=None, telemetry=None, memory=None
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
        telemetry or Telemetry(),
        activity=activity,
        memory=memory,
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


async def test_get_context_records_engine_metrics() -> None:
    catalog = await _catalog()
    telemetry = Telemetry()

    await _usecase(catalog, telemetry=telemetry)(
        GetContextRequest(project_id="railway", task_text="调整 发车时间")
    )

    span = next(r for r in telemetry.records if r.name == "get_context")
    assert span.metrics["recall"] == 3
    assert span.metrics["valid"] + span.metrics["excluded"] == span.metrics["recall"]
    assert span.metrics["assembly_ms"] > 0
    assert span.metrics["bundle_bytes"] > 0
    assert span.metrics["findings"] >= 0


async def test_get_context_recalls_working_memory_into_the_status_section() -> None:
    catalog = await _catalog()
    memory = InMemoryMemory()
    entry = await memory.remember(
        MemoryEntry(
            scope_id="scp-railway",
            kind="decision",
            content="发车时刻调整必须同时重算后续各站",
        )
    )
    usecase = _usecase(catalog, memory=memory)

    result = await usecase(
        GetContextRequest(
            project_id="railway",
            task_text="调整 发车时间",
            scope_id="scp-railway",
        )
    )

    assert [note.content for note in result.bundle.memory_notes] == [
        entry.content
    ]
    assert "working memory (1)" in result.markdown
    assert result.memory_error == ""
    assert result.bundle.budget.used_bytes <= 8000


async def test_get_context_degrades_when_memory_is_unreachable() -> None:
    class _Down:
        async def search(self, scope_id, query, n=8):
            raise SWError("powercontext unreachable")

    catalog = await _catalog()
    result = await _usecase(catalog, memory=_Down())(
        GetContextRequest(
            project_id="railway",
            task_text="调整 发车时间",
            scope_id="scp-railway",
        )
    )

    assert result.bundle.memory_notes == []
    assert result.memory_error == "powercontext unreachable"
    assert result.markdown.startswith("# Context")


async def test_get_context_without_scope_does_not_touch_memory() -> None:
    class _Exploding:
        async def search(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("must not be called without a scope")

    catalog = await _catalog()
    result = await _usecase(catalog, memory=_Exploding())(
        GetContextRequest(project_id="railway", task_text="调整 发车时间")
    )
    assert result.bundle.memory_notes == []


async def test_memory_notes_render_on_a_single_line() -> None:
    """A recalled note can be a whole pasted document; the bundle must not
    break into stray markdown lines."""
    catalog = await _catalog()
    memory = InMemoryMemory()
    await memory.remember(
        MemoryEntry(
            scope_id="scp-railway",
            kind="constraint",
            content=(
                "调整 发车时间 的既有约定\n"
                "第二行含 --- 与 front matter 样式\n" + "很" * 300
            ),
        )
    )

    result = await _usecase(catalog, memory=memory)(
        GetContextRequest(
            project_id="railway",
            task_text="调整 发车时间",
            scope_id="scp-railway",
        )
    )

    (note,) = result.bundle.memory_notes
    assert "\n" not in note.content
    assert len(note.content) <= 200
    # the collapsed note occupies exactly one bullet line in the bundle
    assert (
        "  - constraint: 调整 发车时间 的既有约定 第二行含 ---"
        in result.markdown
    )
    assert "\nid: " not in result.markdown
