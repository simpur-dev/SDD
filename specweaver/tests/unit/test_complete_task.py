from __future__ import annotations

from fakes.activity import InMemoryActivityLog
from fakes.catalog import InMemoryCatalog
from fakes.inference import ScriptedEmbedding
from fakes.memory import InMemoryMemory
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.reconciliation import (
    ReconciliationEngine,
)
from specweaver.application.usecases.complete_task import (
    CompleteTask,
    CompleteTaskRequest,
)
from specweaver.domain.entities import FileChange, TestRun
from specweaver.shared.telemetry import Telemetry


class ScriptedTestRunner:
    def __init__(self, test_run: TestRun) -> None:
        self._tr = test_run

    async def run(self, command: str) -> TestRun:
        result = self._tr.model_copy(deep=True)
        result.command = command
        return result

    async def parse_report(self, uri: str) -> TestRun:
        return self._tr.model_copy(deep=True)


def _usecase(catalog, activity, workspace, test_run, memory=None):
    engine = ReconciliationEngine(ScriptedEmbedding(8))
    runner = ScriptedTestRunner(test_run)
    return CompleteTask(
        engine, catalog, activity, workspace, runner, Telemetry(), memory
    )


def _workspace() -> InMemoryWorkspace:
    files = {
        "src/schedule.py": (
            "def adjust_departure(station):\n    return station\n"
        )
    }
    changes = [FileChange(path="src/schedule.py", change_type="modified")]
    return InMemoryWorkspace(files, ref="head1", changes=changes)


async def test_complete_task_success_records_and_updates() -> None:
    workspace = _workspace()
    catalog = InMemoryCatalog()
    activity = InMemoryActivityLog()
    memory = InMemoryMemory()
    test_run = TestRun(
        id="tr-1", task_id="", total=2, passed=2, failed=0
    )
    usecase = _usecase(catalog, activity, workspace, test_run, memory)

    report = await usecase(
        CompleteTaskRequest(
            project_id="railway",
            task_id="task-1",
            scope_id="scp-1",
            base_ref="base1",
            test_command="pytest",
        )
    )

    assert report.success
    assert report.test_passed == 2
    assert report.files_changed == 1
    assert report.updated_ids
    assert report.change_set_id
    assert len(activity.test_runs) == 1
    assert len(activity.change_sets) == 1
    assert activity.change_sets[0].test_run_id == "tr-1"
    stored = await catalog.get_artifact(report.updated_ids[0])
    assert stored is not None
    entries = await memory.list_entries("scp-1")
    assert any(e.kind == "task_outcome" for e in entries)


async def test_complete_task_failure_keeps_task_open() -> None:
    workspace = _workspace()
    catalog = InMemoryCatalog()
    activity = InMemoryActivityLog()
    test_run = TestRun(
        id="tr-2", task_id="", total=1, passed=0, failed=1
    )
    usecase = _usecase(catalog, activity, workspace, test_run)

    report = await usecase(
        CompleteTaskRequest(
            project_id="railway",
            task_id="task-1",
            scope_id="scp-1",
            base_ref="base1",
        )
    )

    assert not report.success
    assert report.change_set_id is None
    assert report.updated_ids == []
    assert len(activity.test_runs) == 1
    assert len(activity.change_sets) == 0
