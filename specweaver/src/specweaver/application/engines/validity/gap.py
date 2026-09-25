from __future__ import annotations

from ....domain.entities import Artifact
from ....domain.enums import (
    ArtifactType,
    FindingKind,
    RelationKind,
    Severity,
)
from ....domain.ports.catalog import CatalogPort
from ....domain.values import Finding
from .citations import cite

_CHAIN_KINDS = [
    RelationKind.realizes,
    RelationKind.covers,
    RelationKind.tests,
]
_LAYERS = (
    (ArtifactType.design, "design", "a design realizing this requirement"),
    (ArtifactType.code, "code", "an implementation of this requirement"),
    (ArtifactType.test, "test", "tests covering the implementation"),
)


class GapDetector:
    """Checks the requirement -> design -> code -> test coverage chain."""

    def __init__(self, catalog: CatalogPort) -> None:
        self._catalog = catalog

    async def detect(self, artifacts: list[Artifact]) -> list[Finding]:
        findings: list[Finding] = []
        requirements = [
            a for a in artifacts if a.type == ArtifactType.requirement
        ]
        for requirement in requirements:
            connected = await self._catalog.neighbors(
                requirement.id, _CHAIN_KINDS, depth=2
            )
            present = {artifact.type for artifact in connected}
            for layer, label, hint in _LAYERS:
                if layer in present:
                    continue
                findings.append(
                    Finding(
                        kind=FindingKind.gap,
                        severity=Severity.warning,
                        message=(
                            f"Requirement '{requirement.title}' has no "
                            f"{label} layer"
                        ),
                        refs=[cite(requirement)],
                        suggestion=f"Add {hint}.",
                    )
                )
        return findings
