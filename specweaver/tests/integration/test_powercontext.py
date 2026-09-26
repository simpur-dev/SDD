from __future__ import annotations

import pytest
from contract.suites import handoff_suite, memory_suite

from specweaver.adapters.driven.powercontext import (
    PowerContextHandoff,
    PowerContextMemory,
)
from specweaver.application.usecases.create_handoff import (
    CreateHandoff,
    CreateHandoffRequest,
)
from specweaver.shared.telemetry import Telemetry

pytestmark = pytest.mark.integration


async def test_powercontext_memory(pc_adapters) -> None:
    client, project, _scope_id, _source = pc_adapters
    await memory_suite(PowerContextMemory(client), project)


async def test_powercontext_handoff(pc_adapters) -> None:
    client, _project, scope_id, source = pc_adapters
    await handoff_suite(PowerContextHandoff(client), scope_id, source)


async def test_create_handoff_usecase_on_real_backend(pc_adapters) -> None:
    client, project, scope_id, _source = pc_adapters
    usecase = CreateHandoff(PowerContextHandoff(client), Telemetry())
    report = await usecase(
        CreateHandoffRequest(
            project_id=project,
            scope_id=scope_id,
            objective="为铁路调度增加按站调整发车时间",
            state=["已完成 schedule 时刻调整"],
            next_steps=["回归 publish 发布判断"],
            omissions=["publish 尚未回归"],
        )
    )
    assert report.handoff_rev
    resumed = await PowerContextHandoff(client).continue_(
        scope_id, report.handoff_rev
    )
    assert resumed.objective == "为铁路调度增加按站调整发车时间"
    assert resumed.next_steps == ["回归 publish 发布判断"]

    # second handoff with different content must not 409 (unique source ids)
    second = await usecase(
        CreateHandoffRequest(
            project_id=project,
            scope_id=scope_id,
            objective="回归 publish 发布判断",
            state=["schedule/occupancy 已完成"],
            next_steps=["publish 回归收尾"],
        )
    )
    assert second.handoff_rev != report.handoff_rev
