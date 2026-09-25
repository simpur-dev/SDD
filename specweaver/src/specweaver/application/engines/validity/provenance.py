from __future__ import annotations

from ....domain.entities import Artifact
from ....domain.enums import FindingKind, LifecycleStatus, Severity
from ....domain.values import Finding
from .citations import cite

_TENTATIVE_MARKS = frozenset(
    {"tentative", "unverified", "guess", "猜测", "待核实", "draft-spec"}
)


class ProvenanceDetector:
    """Demotes active artifacts whose evidence is explicitly marked tentative."""

    async def detect(self, artifacts: list[Artifact]) -> list[Finding]:
        findings: list[Finding] = []
        for artifact in artifacts:
            if artifact.status != LifecycleStatus.active:
                continue
            marks = {tag.lower() for tag in artifact.tags}
            low = marks & _TENTATIVE_MARKS
            if not low:
                continue
            findings.append(
                Finding(
                    kind=FindingKind.unverified,
                    severity=Severity.info,
                    message=(
                        f"'{artifact.title}' has insufficient evidence "
                        f"({sorted(low)[0]}); treat it as pending verification"
                    ),
                    refs=[cite(artifact)],
                    suggestion=(
                        "Verify against the running system before relying on it."
                    ),
                    needs_confirmation=True,
                )
            )
        return findings
