from __future__ import annotations

import pytest
from fakes.memory import InMemoryMemory

from specweaver.application.usecases.record_decision import (
    RecordDecision,
    RecordDecisionRequest,
)
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry


def _usecase():
    memory = InMemoryMemory()
    return RecordDecision(Telemetry(), memory), memory


async def test_remember_new_decision() -> None:
    usecase, memory = _usecase()
    report = await usecase(
        RecordDecisionRequest(
            project_id="railway",
            scope_id="scp-1",
            decision="发布前统一重算后续站时刻",
            rationale="避免逐站手工修改",
        )
    )
    assert report.action == "remembered"
    assert report.entry_id == "mem-1"
    entry = memory.entries[0]
    assert entry.kind == "decision"
    assert "发布前统一重算" in entry.content
    assert "Rationale:" in entry.content


async def test_revise_superseded_decision() -> None:
    usecase, memory = _usecase()
    await usecase(
        RecordDecisionRequest(
            project_id="railway", scope_id="scp-1", decision="方案A"
        )
    )
    report = await usecase(
        RecordDecisionRequest(
            project_id="railway",
            scope_id="scp-1",
            decision="方案B",
            replaces_entry_id="mem-1",
        )
    )
    assert report.action == "revised"
    assert memory.entries[0].content == "方案B"


async def test_retire_decision() -> None:
    usecase, memory = _usecase()
    await usecase(
        RecordDecisionRequest(
            project_id="railway", scope_id="scp-1", decision="方案A"
        )
    )
    report = await usecase(
        RecordDecisionRequest(
            project_id="railway",
            scope_id="scp-1",
            decision="业务方向取消",
            retire_entry_id="mem-1",
        )
    )
    assert report.action == "retired"
    assert memory.entries[0].active is False


async def test_guard_errors() -> None:
    usecase, _ = _usecase()
    with pytest.raises(SWError):
        await usecase(RecordDecisionRequest(project_id="p"))
    with pytest.raises(SWError):
        await usecase(
            RecordDecisionRequest(project_id="p", scope_id="scp-1")
        )
    with pytest.raises(SWError):
        await usecase(
            RecordDecisionRequest(
                project_id="p",
                scope_id="scp-1",
                decision="x",
                replaces_entry_id="mem-1",
                retire_entry_id="mem-2",
            )
        )
    with pytest.raises(SWError):
        await usecase(
            RecordDecisionRequest(
                project_id="p",
                scope_id="scp-1",
                decision="x",
                replaces_entry_id="missing",
            )
        )


async def test_no_memory_port_raises() -> None:
    usecase = RecordDecision(Telemetry(), None)
    with pytest.raises(SWError):
        await usecase(
            RecordDecisionRequest(
                project_id="p", scope_id="scp-1", decision="x"
            )
        )
