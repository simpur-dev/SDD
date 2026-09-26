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


def _sort_key(
    artifact: Artifact, relevance: dict[str, float]
) -> tuple[int, float, str, str]:
    """Link importance first (type), then retrieval relevance inside the type.

    Relevance never re-orders across types: constraints and requirements keep
    their place in the goal section regardless of score (docs/01 §4.4), so a
    low-scoring rule cannot be pushed behind code.
    """
    return (
        _TYPE_ORDER.get(artifact.type, 9),
        -relevance.get(artifact.id, 0.0),
        artifact.module or "",
        artifact.id,
    )


@dataclass
class Sections:
    goal_and_constraints: list[Artifact]
    design_and_implementation: list[Artifact]
    verification: list[Artifact]


def map_sections(
    artifacts: list[Artifact],
    relevance: dict[str, float] | None = None,
) -> Sections:
    scores = relevance or {}
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
        goal_and_constraints=sorted(goal, key=lambda a: _sort_key(a, scores)),
        design_and_implementation=sorted(
            design, key=lambda a: _sort_key(a, scores)
        ),
        verification=sorted(
            verification, key=lambda a: _sort_key(a, scores)
        ),
    )
