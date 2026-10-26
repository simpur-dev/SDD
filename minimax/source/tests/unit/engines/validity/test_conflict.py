from __future__ import annotations

from specweaver.application.engines.validity import ConflictDetector
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType, FindingKind


def _requirement(artifact_id: str, item: str) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=ArtifactType.requirement,
        module="schedule",
        title=artifact_id,
        content=f"# 标题\n- {item}\n",
    )


async def test_numeric_value_conflict() -> None:
    artifacts = [
        _requirement("REQ-1", "发车时间不得早于 6 点"),
        _requirement("REQ-2", "发车时间不得早于 8 点"),
    ]
    findings = await ConflictDetector().detect(artifacts)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.conflict
    assert {c.artifact_id for c in findings[0].refs} == {
        "REQ-1",
        "REQ-2",
    }
    assert findings[0].needs_confirmation


async def test_polarity_conflict() -> None:
    artifacts = [
        _requirement("REQ-1", "必须允许按站调整发车时间"),
        _requirement("REQ-2", "禁止按站调整发车时间"),
    ]
    findings = await ConflictDetector().detect(artifacts)
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.conflict


async def test_consistent_constraints_no_conflict() -> None:
    artifacts = [
        _requirement("REQ-1", "发车时间不得早于 6 点"),
        _requirement("REQ-2", "区间占用不得超过 5 列"),
    ]
    assert await ConflictDetector().detect(artifacts) == []
