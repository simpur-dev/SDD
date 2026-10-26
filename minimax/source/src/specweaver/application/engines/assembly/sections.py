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

# Requirement and rule are one tier: both are the "effective old constraints"
# the bundle exists to surface, so neither may push the other down the page on
# the strength of its type alone.
_TIER = {
    ArtifactType.requirement: 0,
    ArtifactType.rule: 0,
    ArtifactType.design: 1,
    ArtifactType.code: 1,
    ArtifactType.test: 2,
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
) -> tuple[int, float, int, int, str, str]:
    """Section tier first, then retrieval relevance, then type.

    A constraint still never falls behind code - the tier keeps that promise
    (docs/01 §4.4). What must not happen is a *type* inside one tier winning a
    scarce slot from a better-matched one: measured on the gold set, ordering
    rules ahead of requirements spent 1500 bytes on an unrelated publish rule
    in 5 of 6 cases while the requirement the task was actually about, and the
    design artifact ranked third by score, were dropped (docs/01 §11).

    The constraint floor injects active requirements/rules with no score at
    all; those fall behind every scored candidate in the tier and then order by
    task-token overlap rather than by ``(module, id)``, which handed slots to
    whichever id sorted first.
    """
    score = relevance.get(artifact.id, 0.0)
    fallback = -task_overlap(task_text, artifact) if score <= 0.0 else 0
    return (
        _TIER.get(artifact.type, 9),
        -score,
        _TYPE_ORDER.get(artifact.type, 9),
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

    def key(
        artifact: Artifact,
    ) -> tuple[int, float, int, int, str, str]:
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
