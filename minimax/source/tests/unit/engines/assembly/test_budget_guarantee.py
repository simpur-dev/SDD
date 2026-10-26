"""Emitting more than the declared budget is a contract break, not a rounding note.

The Budgeter decides with a byte *model*; these tests pin the model's outcome
against the rendered markdown, which is what an Agent actually receives. The
regression it guards is the ④ "sources cited" line: every artifact kept adds
its id there, so a budget that looked met on paper could overflow by the whole
id list.
"""
from __future__ import annotations

import pytest

from specweaver.application.engines.assembly import (
    AssemblyEngine,
    entry_block,
    render_markdown,
)
from specweaver.application.engines.assembly.budget import entry_cost
from specweaver.domain.entities import Artifact, Task, TestRun
from specweaver.domain.enums import ArtifactType, FindingKind, Severity
from specweaver.domain.rules import byte_size
from specweaver.domain.values import Citation, Finding, MemoryNote, SourceRef

_LONG_ID = "occupancy-window-validation"


def _artifact(index: int, artifact_type: ArtifactType) -> Artifact:
    return Artifact(
        id=f"{artifact_type.value.upper()}-{index}-{_LONG_ID}",
        project_id="p",
        type=artifact_type,
        title=f"构件 {index}",
        content="约束与验收口径 " * 12,
    )


def _corpus() -> list[Artifact]:
    return [
        _artifact(i, kind)
        for kind in (
            ArtifactType.requirement,
            ArtifactType.design,
            ArtifactType.code,
            ArtifactType.test,
        )
        for i in range(4)
    ]


def _findings() -> list[Finding]:
    return [
        Finding(
            kind=FindingKind.conflict,
            severity=Severity.warning,
            message="两条需求对同一行为给出互斥口径 " * 3,
            suggestion="确认哪一条仍然生效",
        )
        for _ in range(3)
    ]


def _notes() -> list[MemoryNote]:
    return [
        MemoryNote(
            kind="decision",
            content="先改接口签名再补回归测试 " * 3,
            citation=Citation(
                artifact_id="mem-1",
                source=SourceRef(
                    uri="powercontext://memory/scp-1",
                    locator="mem-1",
                    kind="memory",
                ),
            ),
        )
        for _ in range(3)
    ]


def _test_run() -> TestRun:
    return TestRun(
        id="tr-1",
        task_id="task-1",
        passed=13,
        failed=0,
        total=13,
        skipped=0,
        commit_ref="0a1b2c3",
        command="python -m pytest -q",
    )


async def _assemble(max_bytes: int, title: str = "给调度接口加校验"):
    task = Task(id="task-1", project_id="p", title=title)
    return await AssemblyEngine(max_bytes=max_bytes).run(
        task,
        _corpus(),
        _findings(),
        last_test_run=_test_run(),
        memory_notes=_notes(),
    )


_LONG_TITLE = "为列车按站调整发车时间并重算后续各站时刻，检查占用冲突并阻止发布" * 3


@pytest.mark.parametrize(
    "max_bytes", [1600, 2400, 3200, 4800, 6400, 7700, 8000]
)
async def test_rendered_bundle_never_exceeds_its_declared_budget(
    max_bytes: int,
) -> None:
    bundle = await _assemble(max_bytes)
    assert bundle.budget is not None
    assert bundle.budget.used_bytes <= max_bytes
    assert byte_size(render_markdown(bundle)) <= max_bytes


@pytest.mark.parametrize(
    "max_bytes", [2600, 3400, 4200, 5000, 6000, 7000, 7700, 8000]
)
async def test_a_utf8_heavy_title_cannot_push_the_bundle_over_budget(
    max_bytes: int,
) -> None:
    """The frame is not a constant.

    The title costs 3 bytes per character and the "truncated" warning costs a
    line no artifact paid for; the railway demo caught a build that was 8269
    bytes on a 8000-byte promise because of exactly those two.
    """
    bundle = await _assemble(max_bytes, title=_LONG_TITLE)
    assert bundle.budget is not None
    assert bundle.budget.used_bytes <= max_bytes
    markdown = render_markdown(bundle)
    dropped_anything = (
        bundle.goal_and_constraints
        or bundle.design_and_implementation
        or bundle.verification
    )
    if dropped_anything:  # while there is content left to cut, it must fit
        assert byte_size(markdown) <= max_bytes
    else:  # the one sanctioned overflow says so out loud
        assert "exceeds this budget" in markdown


async def test_tight_budget_keeps_the_constraint_floor_first() -> None:
    bundle = await _assemble(2400)
    assert bundle.goal_and_constraints
    assert all(
        a.type in (ArtifactType.requirement, ArtifactType.rule)
        for a in bundle.goal_and_constraints
    )


async def test_budget_below_the_bare_frame_announces_it() -> None:
    bundle = await _assemble(400)
    markdown = render_markdown(bundle)
    assert bundle.budget is not None
    assert bundle.budget.used_bytes > 400
    assert not bundle.goal_and_constraints
    # the only honest answer: no content decision can fit, so ⑥ says so loudly
    assert "exceeds this budget" in markdown


@pytest.mark.parametrize(
    "artifact_id", ["REQ-1", f"REQ-1-{_LONG_ID}", f"REQ-1-{_LONG_ID}-2"]
)
def test_entry_cost_charges_block_plus_the_id_the_citation_line_repeats(
    artifact_id: str,
) -> None:
    artifact = Artifact(
        id=artifact_id,
        project_id="p",
        type=ArtifactType.requirement,
        title="需求标题",
        content="same body",
    )
    # the block itself, one ", "-joined id in ④ "sources cited", and the blank
    # line the renderer puts between blocks
    assert entry_cost(artifact) == (
        byte_size(entry_block(artifact)) + byte_size(artifact_id) + 2
    )
