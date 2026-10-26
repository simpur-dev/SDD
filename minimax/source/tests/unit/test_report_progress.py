from __future__ import annotations

import pytest
from fakes.handoff import InMemoryHandoff
from fakes.memory import InMemoryMemory

from specweaver.application.usecases.create_handoff import CreateHandoff
from specweaver.application.usecases.report_progress import (
    ReportProgress,
    ReportProgressRequest,
)
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry


async def test_progress_note_recorded() -> None:
    memory = InMemoryMemory()
    usecase = ReportProgress(Telemetry(), memory)
    report = await usecase(
        ReportProgressRequest(
            project_id="railway",
            scope_id="scp-1",
            note="schedule 调整函数已完成并通过回归",
        )
    )
    assert report.entry_id
    assert report.handoff_rev is None
    assert memory.entries[0].kind == "progress"


async def test_progress_with_handoff_composition() -> None:
    memory = InMemoryMemory()
    handoff_port = InMemoryHandoff()
    usecase = ReportProgress(
        Telemetry(),
        memory,
        CreateHandoff(handoff_port, Telemetry()),
    )
    report = await usecase(
        ReportProgressRequest(
            project_id="railway",
            scope_id="scp-1",
            note="occupancy 联动复核完成",
            update_handoff=True,
            next_steps=["发布前跑全量回归"],
        )
    )
    assert report.handoff_rev
    resumed = await handoff_port.continue_(
        "scp-1", report.handoff_rev
    )
    assert resumed.progress == "occupancy 联动复核完成"
    assert resumed.next_steps == ["发布前跑全量回归"]


async def test_progress_guards() -> None:
    memory = InMemoryMemory()
    usecase = ReportProgress(Telemetry(), memory)
    with pytest.raises(SWError):
        await usecase(
            ReportProgressRequest(project_id="p", note="x")
        )
    with pytest.raises(SWError):
        await usecase(
            ReportProgressRequest(project_id="p", scope_id="scp-1")
        )
    no_handoff = ReportProgress(Telemetry(), memory, None)
    with pytest.raises(SWError):
        await no_handoff(
            ReportProgressRequest(
                project_id="p",
                scope_id="scp-1",
                note="x",
                update_handoff=True,
            )
        )
