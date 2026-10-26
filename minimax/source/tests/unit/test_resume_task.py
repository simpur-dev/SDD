from __future__ import annotations

from fakes.catalog import InMemoryCatalog, InMemoryHybridSearch
from fakes.handoff import InMemoryHandoff
from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

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
from specweaver.application.usecases.resume_task import (
    ResumeTask,
    ResumeTaskRequest,
)
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType
from specweaver.domain.values import SourceRef
from specweaver.shared.telemetry import Telemetry


async def _seeded_catalog() -> InMemoryCatalog:
    catalog = InMemoryCatalog()
    for artifact in (
        Artifact(
            id="REQ-1",
            project_id="railway",
            type=ArtifactType.requirement,
            title="按站调整发车时间",
            content="# 需求\n- 应能调整发车时间",
        ),
        Artifact(
            id="CODE-1",
            project_id="railway",
            type=ArtifactType.code,
            title="schedule",
            content="def adjust_departure():\n    return True\n",
        ),
        Artifact(
            id="TST-1",
            project_id="railway",
            type=ArtifactType.test,
            title="test_schedule",
            content="def test_adjust_departure():\n    assert True\n",
        ),
    ):
        await catalog.upsert_artifact(artifact)
    return catalog


def _get_context(catalog: InMemoryCatalog, workspace: InMemoryWorkspace):
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
        workspace,
    )


async def test_resume_reports_checksum_mismatch() -> None:
    catalog = await _seeded_catalog()
    workspace = InMemoryWorkspace(
        {"src/schedule.py": "def changed():\n    return 1\n"}, ref="head1"
    )
    stale = Artifact(
        id="STALE-1",
        project_id="railway",
        type=ArtifactType.code,
        title="stale",
        content="old",
        source=SourceRef(
            uri="src/schedule.py", checksum="sha256:recorded-old"
        ),
    )
    await catalog.upsert_artifact(stale)

    resume = ResumeTask(
        catalog,
        None,
        workspace,
        _get_context(catalog, workspace),
        Telemetry(),
    )
    report = await resume(
        ResumeTaskRequest(
            project_id="railway",
            scope_id="scp-1",
            objective="调整 发车时间",
        )
    )

    assert report.handoff_resumed is False
    assert len(report.mismatches) == 1
    mismatch = report.mismatches[0]
    assert mismatch.artifact_id == "STALE-1"
    assert "checksum" in mismatch.issue
    assert report.context.markdown.startswith("# Context")


async def test_resume_continues_handoff_without_mismatch() -> None:
    catalog = await _seeded_catalog()
    workspace = InMemoryWorkspace(
        {"src/schedule.py": "def current():\n    return 1\n"}, ref="head1"
    )
    actual_checksum = await workspace.checksum("src/schedule.py")
    fresh = Artifact(
        id="FRESH-1",
        project_id="railway",
        type=ArtifactType.code,
        title="fresh",
        content="current",
        source=SourceRef(uri="src/schedule.py", checksum=actual_checksum),
    )
    await catalog.upsert_artifact(fresh)

    handoff = InMemoryHandoff()
    draft = await handoff.prepare_current(
        _draft("scp-1", "继续按站调整发车时间")
    )
    committed = await handoff.commit(draft)

    resume = ResumeTask(
        catalog,
        handoff,
        workspace,
        _get_context(catalog, workspace),
        Telemetry(),
    )
    report = await resume(
        ResumeTaskRequest(
            project_id="railway",
            scope_id="scp-1",
            handoff_rev=committed.rev,
        )
    )

    assert report.handoff_resumed is True
    assert report.objective == "继续按站调整发车时间"
    assert report.next_steps == ["核对下游占用与发布"]
    assert report.mismatches == []


def _draft(scope_id: str, objective: str):
    from specweaver.domain.ports.handoff import HandoffDraft

    return HandoffDraft(
        scope_id=scope_id,
        objective=objective,
        state=["schedule 时刻调整已完成"],
        next_steps=["核对下游占用与发布"],
    )
