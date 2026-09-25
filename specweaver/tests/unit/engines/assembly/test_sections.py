from __future__ import annotations

from specweaver.application.engines.assembly import map_sections
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType


def _a(artifact_id: str, artifact_type: ArtifactType) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=artifact_type,
        title=artifact_id,
    )


def test_map_sections_groups_by_type() -> None:
    sections = map_sections(
        [
            _a("CODE-1", ArtifactType.code),
            _a("REQ-1", ArtifactType.requirement),
            _a("RULE-1", ArtifactType.rule),
            _a("TST-1", ArtifactType.test),
            _a("DES-1", ArtifactType.design),
        ]
    )
    assert {a.id for a in sections.goal_and_constraints} == {
        "REQ-1",
        "RULE-1",
    }
    assert {a.id for a in sections.design_and_implementation} == {
        "CODE-1",
        "DES-1",
    }
    assert {a.id for a in sections.verification} == {"TST-1"}


def test_sections_sorted_deterministically() -> None:
    sections = map_sections(
        [
            _a("REQ-2", ArtifactType.requirement),
            _a("REQ-1", ArtifactType.requirement),
        ]
    )
    assert [a.id for a in sections.goal_and_constraints] == [
        "REQ-1",
        "REQ-2",
    ]
