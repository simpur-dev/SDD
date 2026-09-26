from __future__ import annotations

import re
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

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|[一-鿿]{2,}")


def task_overlap(task_text: str, artifact: Artifact) -> int:
    """How many of the task's own tokens the artifact repeats.

    A deterministic tie-breaker, not a relevance claim: it only decides
    between candidates the retriever gave no score to.
    """
    tokens = {t.lower() for t in _TOKEN_RE.findall(task_text)}
    if not tokens:
        return 0
    haystack = f"{artifact.title}\n{artifact.content}".lower()
    return sum(1 for token in tokens if token in haystack)


def _sort_key(
    artifact: Artifact, relevance: dict[str, float], task_text: str
) -> tuple[int, float, int, str, str]:
    """Link importance first (type), then retrieval relevance inside the type.

    Relevance never re-orders across types: constraints and requirements keep
    their place in the goal section regardless of score (docs/01 §4.4), so a
    low-scoring rule cannot be pushed behind code.

    The constraint floor injects active requirements/rules with no score at
    all; ordering those by ``(module, id)`` alone hands a scarce budget slot to
    whichever id sorts first, which is what cost us gold hits at 1500 bytes
    (docs/01 §11). They fall back to task-token overlap instead; scored
    candidates keep the exact order they had.
    """
    score = relevance.get(artifact.id, 0.0)
    fallback = (
        -task_overlap(task_text, artifact) if score <= 0.0 else 0
    )
    return (
        _TYPE_ORDER.get(artifact.type, 9),
        -score,
        fallback,
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
    task_text: str = "",
) -> Sections:
    scores = relevance or {}

    def key(artifact: Artifact) -> tuple[int, float, int, str, str]:
        return _sort_key(artifact, scores, task_text)

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
        goal_and_constraints=sorted(goal, key=key),
        design_and_implementation=sorted(design, key=key),
        verification=sorted(verification, key=key),
    )
