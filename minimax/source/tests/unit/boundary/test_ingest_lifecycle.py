"""Batch-6 behaviour guards: duplicate ids, tombstones, vacuous green,
resume error surfacing (audits C2/C5/B2/B4)."""
from __future__ import annotations

from fakes.activity import InMemoryActivityLog
from fakes.catalog import InMemoryCatalog
from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.ingestion import IngestionEngine
from specweaver.application.usecases.complete_task import (
    CompleteTask,
    CompleteTaskRequest,
)
from specweaver.application.usecases.get_context import ContextResult
from specweaver.application.usecases.ingest_project import (
    IngestProject,
    IngestProjectRequest,
)
from specweaver.application.usecases.resume_task import (
    ResumeTask,
    ResumeTaskRequest,
)
from specweaver.domain.entities import FileChange, Task, TestRun
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry

REQ_A = "---\nid: REQ-01\n---\n# A\n- 约束甲\n"
REQ_B = "---\nid: REQ-01\n---\n# B duplicate\n- 约束乙\n"


async def test_engine_reports_duplicate_ids() -> None:
    workspace = InMemoryWorkspace(
        {"specs/a.md": REQ_A, "specs/b.md": REQ_B}
    )
    result = await IngestionEngine(ScriptedEmbedding(8)).run(
        "p", workspace, {}
    )
    assert result.duplicate_ids == ["REQ-1"]


async def test_ingest_tombstones_missing_source_files() -> None:
    files = {"specs/a.md": REQ_A, "specs/gone.md": "---\nid: REQ-02\n---\n# G\n"}
    workspace = InMemoryWorkspace(files)
    catalog = InMemoryCatalog()
    usecase = IngestProject(
        IngestionEngine(ScriptedEmbedding(8)),
        catalog,
        workspace,
        Telemetry(),
    )
    first = await usecase(
        IngestProjectRequest(
            project_id="p", register_source=False
        )
    )
    assert first.added == 2
    workspace.files.pop("specs/gone.md")
    second = await usecase(
        IngestProjectRequest(
            project_id="p", register_source=False
        )
    )
    assert second.deprecated == 1
    stored = await catalog.get_artifact("p", "REQ-2")
    assert stored is not None
    assert stored.status.value == "deprecated"


class _EmptyRunner:
    async def run(self, command: str) -> TestRun:
        return TestRun(id="tr-x", task_id="", total=0, passed=0, failed=0)

    async def parse_report(self, uri: str) -> TestRun:  # pragma: no cover
        raise NotImplementedError


async def test_zero_total_run_blocks_reconciliation() -> None:
    """Audit B2: 'no tests ran' is NOT a green completion."""
    catalog = InMemoryCatalog()
    workspace = InMemoryWorkspace(
        {"src/a.py": "x = 1\n"},
        changes=[FileChange(path="src/a.py", change_type="added")],
    )
    usecase = CompleteTask(
        _noop_engine(), catalog, InMemoryActivityLog(), workspace,
        _EmptyRunner(), Telemetry(),
    )
    report = await usecase(
        CompleteTaskRequest(
            project_id="p",
            task_id="t",
            base_ref="base1",
            register_outcome=False,
        )
    )
    assert report.success is False
    assert report.change_set_id is None


def _noop_engine():
    from specweaver.application.engines.reconciliation import (
        ReconciliationEngine,
    )

    return ReconciliationEngine(ScriptedEmbedding(8))


class _BrokenHandoff:
    async def continue_(self, scope_id: str, rev: str):
        raise SWError("powercontext 404 on handoff/continue")


class _NoContext:
    async def __call__(self, request) -> ContextResult:
        from specweaver.domain.entities import ContextBundle

        task = Task(id="t1", project_id="p", title="x")
        return ContextResult(
            bundle=ContextBundle(task=task),
            markdown="# Context",
            excluded=[],
        )


async def test_resume_surfaces_handoff_error() -> None:
    resume = ResumeTask(
        None, _BrokenHandoff(), InMemoryWorkspace(), _NoContext(),
        Telemetry(),
    )
    report = await resume(
        ResumeTaskRequest(
            project_id="p",
            scope_id="scp-1",
            handoff_rev="handoff:art:7",
            objective="继续",
        )
    )
    assert report.handoff_resumed is False
    assert "404" in report.handoff_error
