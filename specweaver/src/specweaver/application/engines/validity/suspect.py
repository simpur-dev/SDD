from __future__ import annotations

from ....domain.entities import Artifact
from ....domain.enums import FindingKind, LifecycleStatus, Severity
from ....domain.ports.catalog import CatalogPort
from ....domain.values import Finding
from .citations import cite


class SuspectDetector:
    """Flags downstream artifacts based on a non-active upstream version."""

    def __init__(self, catalog: CatalogPort) -> None:
        self._catalog = catalog

    async def detect(self, artifacts: list[Artifact]) -> list[Finding]:
        if self._catalog is None:
            return []
        findings: list[Finding] = []
        for artifact in artifacts:
            for ref in artifact.based_on:
                upstream = await self._catalog.get_artifact(ref)
                if upstream is None or upstream.status == LifecycleStatus.active:
                    continue
                findings.append(
                    Finding(
                        kind=FindingKind.suspect,
                        severity=Severity.warning,
                        message=(
                            f"'{artifact.title}' is based on {ref}, whose "
                            f"status is {upstream.status}"
                        ),
                        refs=[cite(artifact), cite(upstream)],
                        suggestion=(
                            "Review and update this downstream artifact "
                            "against the current upstream version."
                        ),
                    )
                )
        return findings
