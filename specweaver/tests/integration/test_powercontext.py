from __future__ import annotations

import pytest
from contract.suites import handoff_suite, memory_suite

from specweaver.adapters.driven.powercontext import (
    PowerContextHandoff,
    PowerContextMemory,
)

pytestmark = pytest.mark.integration


async def test_powercontext_memory(pc_adapters) -> None:
    client, scope_id, _source = pc_adapters
    await memory_suite(PowerContextMemory(client), scope_id)


async def test_powercontext_handoff(pc_adapters) -> None:
    client, scope_id, source = pc_adapters
    await handoff_suite(PowerContextHandoff(client), scope_id, source)
