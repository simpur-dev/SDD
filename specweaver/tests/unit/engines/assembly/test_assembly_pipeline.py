from __future__ import annotations

from specweaver.application.engines.assembly import AssemblyEngine
from specweaver.domain.entities import Artifact, Task
from specweaver.domain.enums import (
    ArtifactType,
    FindingKind,
    Severity,
)
from specweaver.domain.values import Finding


def _a(artifact_id: str, artifact_type: ArtifactType) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=artifact_type,
        title=artifact_id,
        content="body",
    )


async def test_assembly_builds_bundle_within_budget() -> None:
    task = Task(id="task-1", project_id="p", title="任务")
    valid = [
        _a("REQ-1", ArtifactType.requirement),
        _a("CODE-1", ArtifactType.code),
        _a("TST-1", ArtifactType.test),
    ]
    finding = Finding(
        kind=FindingKind.gap,
        severity=Severity.warning,
        message="missing layer",
    )
    bundle = await AssemblyEngine(max_bytes=8000).run(
        task, valid, [finding]
    )
    assert [a.id for a in bundle.goal_and_constraints] == ["REQ-1"]
    assert [a.id for a in bundle.design_and_implementation] == [
        "CODE-1"
    ]
    assert [a.id for a in bundle.verification] == ["TST-1"]
    assert len(bundle.citations) == 3
    assert bundle.findings == [finding]
    assert bundle.budget is not None
    assert bundle.budget.used_bytes <= 8000
