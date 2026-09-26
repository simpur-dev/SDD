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
                upstream = await self._catalog.get_artifact(
                    artifact.project_id, ref
                )
                if upstream is None:
                    # audit B5: a dangling reference is exactly what a
                    # downstream reviewer needs to see
                    findings.append(
                        Finding(
                            kind=FindingKind.suspect,
                            severity=Severity.warning,
                            message=(
                                f"'{artifact.title}' references {ref}, "
                                "which is missing from the catalog"
                            ),
                            refs=[cite(artifact)],
                            suggestion=(
                                "Ingest the missing upstream artifact or "
                                "re-point the reference."
                            ),
                        )
                    )
                    continue
                if upstream.status == LifecycleStatus.active:
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
