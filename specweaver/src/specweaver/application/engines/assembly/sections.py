from __future__ import annotations

from dataclasses import dataclass

from ....domain.entities import Artifact
from ....domain.enums import ArtifactType

GOAL_TYPES = frozenset({ArtifactType.requirement, ArtifactType.rule})
DESIGN_TYPES = frozenset({ArtifactType.design, ArtifactType.code})
VERIFY_TYPES = frozenset({ArtifactType.test})

_TYPE_ORDER = {
    ArtifactType.rule: 0,
    ArtifactType.requirement: 1,
    ArtifactType.design: 2,
    ArtifactType.code: 3,
    ArtifactType.test: 4,
}


def _sort_key(artifact: Artifact) -> tuple[int, str, str]:
    return (
        _TYPE_ORDER.get(artifact.type, 9),
        artifact.module or "",
        artifact.id,
    )


@dataclass
class Sections:
    goal_and_constraints: list[Artifact]
    design_and_implementation: list[Artifact]
    verification: list[Artifact]


def map_sections(artifacts: list[Artifact]) -> Sections:
    goal: list[Artifact] = []
    design: list[Artifact] = []
    verification: list[Artifact] = []
    for artifact in artifacts:
        if artifact.type in GOAL_TYPES:
            goal.append(artifact)
        elif artifact.type in DESIGN_TYPES:
            design.append(artifact)
        elif artifact.type in VERIFY_TYPES:
            verification.append(artifact)
    return Sections(
        goal_and_constraints=sorted(goal, key=_sort_key),
        design_and_implementation=sorted(design, key=_sort_key),
        verification=sorted(verification, key=_sort_key),
    )
