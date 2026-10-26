from __future__ import annotations

import hashlib

import pytest
from fakes.activity import InMemoryActivityLog
from fakes.catalog import InMemoryCatalog
from fakes.memory import InMemoryMemory
from fakes.workspace import InMemoryWorkspace

from specweaver.application.usecases.verify_state import (
    VerifyState,
    VerifyStateRequest,
)
from specweaver.domain.entities import Artifact, ChangeSet, TestRun
from specweaver.domain.enums import ArtifactType
from specweaver.domain.values import SourceRef
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry

SRC = "src/schedule.py"
CONTENT = "def f():\n    return 1\n"


def _checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _seed() -> tuple[InMemoryCatalog, InMemoryWorkspace]:
    catalog = InMemoryCatalog()
    workspace = InMemoryWorkspace({SRC: CONTENT}, ref="head9")
    await catalog.upsert_artifact(
        Artifact(
            id="CODE-1",
            project_id="railway",
            type=ArtifactType.code,
            title="schedule",
            content=CONTENT,
            source=SourceRef(uri=SRC, checksum=_checksum(CONTENT)),
        )
    )
    await catalog.upsert_artifact(
        Artifact(
            id="CODE-2",
            project_id="railway",
            type=ArtifactType.code,
            title="gone",
            content="x",
            source=SourceRef(uri="src/gone.py", checksum="sha256:zz"),
        )
    )
    await catalog.upsert_artifact(
        Artifact(
            id="RULE-1",
            project_id="railway",
            type=ArtifactType.rule,
            module="schedule",
            title="最小站间隔",
            content="- 相邻站间隔不得低于 3 分钟",
        )
    )
    return catalog, workspace


async def test_three_way_report() -> None:
    catalog, workspace = await _seed()
    activity = InMemoryActivityLog()
    await activity.record_change_set(
        ChangeSet(
            id="cs-1",
            project_id="railway",
            task_id="t",
            head_checksum="head9",
        )
    )
    await activity.record_test_run(
        TestRun(id="tr-1", task_id="t", project_id="railway",
                total=5, passed=5, failed=0)
    )
    memory = InMemoryMemory()
    usecase = VerifyState(
        catalog, workspace, Telemetry(), activity, memory
    )
    report = await usecase(
        VerifyStateRequest(project_id="railway", scope_id="scp-1")
    )
    assert report.checked == 3
    assert [m.artifact_id for m in report.mismatches] == ["CODE-2"]
    assert report.mismatches[0].issue.startswith("source file")
    assert report.change_set_stale is False
    assert report.last_test_run_id == "tr-1"
    assert report.test_report == "absent"
    assert report.rules_in_catalog == 1
    assert report.constraint_entries_in_memory == 0
    assert any("never precipitated" in n for n in report.notes)
    assert any("no junit report_ref" in n for n in report.notes)


async def test_stale_change_set_and_diverged_report() -> None:
    class _Runner:
        async def run(self, command: str) -> TestRun:  # pragma: no cover
            raise NotImplementedError

        async def parse_report(self, uri: str) -> TestRun:
            return TestRun(id="tr-x", task_id="t", total=9,
                           passed=8, failed=1)

    catalog, workspace = await _seed()
    activity = InMemoryActivityLog()
    await activity.record_change_set(
        ChangeSet(id="cs-9", project_id="railway", task_id="t",
                  head_checksum="older")
    )
    await activity.record_test_run(
        TestRun(id="tr-9", task_id="t", project_id="railway",
                total=5, passed=5, failed=0, report_ref="junit.xml")
    )
    usecase = VerifyState(
        catalog, workspace, Telemetry(), activity, None, _Runner()
    )
    report = await usecase(VerifyStateRequest(project_id="railway"))
    assert report.change_set_stale is True
    assert report.test_report == "diverged"
    assert any("complete_task" in n for n in report.notes)


async def test_requires_catalog() -> None:
    usecase = VerifyState(
        None, InMemoryWorkspace(), Telemetry()
    )
    with pytest.raises(SWError):
        await usecase(VerifyStateRequest(project_id="p"))


class _BrokenActivity:
    async def list_change_sets(self, project_id: str) -> list:
        raise SWError("seekdb is down")

    async def list_test_runs(self, project_id: str) -> list:  # pragma: no cover
        raise AssertionError("must not be reached")


class _BrokenMemory:
    async def list_entries(self, scope_id: str, **kwargs) -> list:
        raise SWError("powercontext is down")


async def test_backend_outages_degrade_into_notes() -> None:
    """A diagnostic report must survive an unreachable backend (M5 audit)."""
    catalog, workspace = await _seed()
    usecase = VerifyState(
        catalog,
        workspace,
        Telemetry(),
        _BrokenActivity(),
        _BrokenMemory(),
    )

    report = await usecase(
        VerifyStateRequest(project_id="railway", scope_id="scp-1")
    )

    assert report.checked == 3
    assert [m.artifact_id for m in report.mismatches] == ["CODE-2"]
    assert report.last_change_set_id is None
    assert report.constraint_entries_in_memory is None
    assert "activity check unavailable: seekdb is down" in report.notes
    assert "memory check unavailable: powercontext is down" in report.notes
