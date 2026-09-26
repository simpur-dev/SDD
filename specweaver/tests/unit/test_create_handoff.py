from __future__ import annotations

import pytest
from fakes.handoff import InMemoryHandoff

from specweaver.application.usecases.create_handoff import (
    CreateHandoff,
    CreateHandoffRequest,
)
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry


async def test_create_handoff_commits_and_returns_rev() -> None:
    handoff = InMemoryHandoff()
    telemetry = Telemetry()
    usecase = CreateHandoff(handoff, telemetry)
    report = await usecase(
        CreateHandoffRequest(
            project_id="railway",
            scope_id="scp-1",
            objective="按站调整发车时间",
            state=["schedule 已改"],
            next_steps=["回归 publish"],
            omissions=["publish 未验证"],
        )
    )
    assert report.handoff_rev
    assert report.objective == "按站调整发车时间"
    assert report.next_steps == ["回归 publish"]
    assert report.unverified == ["publish 未验证"]
    resumed = await handoff.continue_(report.scope_id, report.handoff_rev)
    assert "schedule" in resumed.progress
    assert telemetry.records[0].name == "create_handoff"


async def test_create_handoff_requires_scope() -> None:
    usecase = CreateHandoff(InMemoryHandoff(), Telemetry())
    with pytest.raises(SWError):
        await usecase(CreateHandoffRequest(project_id="railway"))


async def test_create_handoff_requires_state_claim() -> None:
    usecase = CreateHandoff(InMemoryHandoff(), Telemetry())
    with pytest.raises(SWError):
        await usecase(
            CreateHandoffRequest(project_id="railway", scope_id="scp-1")
        )


async def test_create_handoff_requires_objective() -> None:
    usecase = CreateHandoff(InMemoryHandoff(), Telemetry())
    with pytest.raises(SWError):
        await usecase(
            CreateHandoffRequest(
                project_id="railway",
                scope_id="scp-1",
                objective="   ",
                state=["s1"],
            )
        )
