from __future__ import annotations

from pydantic import BaseModel

from ....domain.entities import Artifact
from ....domain.ports.catalog import ScoredArtifact
from ....domain.ports.workspace import WorkspacePort
from ....domain.values import Finding
from .conflict import ConflictDetector
from .gap import GapDetector
from .lifecycle import LifecycleValidator, Verdict
from .provenance import ProvenanceDetector
from .suspect import SuspectDetector


class ExcludedArtifact(BaseModel):
    artifact: Artifact
    reasons: list[str]


class ValidityResult(BaseModel):
    valid: list[Artifact]
    excluded: list[ExcludedArtifact]
    findings: list[Finding]


class ValidityEngine:
    """Split candidates into currently-valid vs excluded and collect findings."""

    def __init__(
        self,
        lifecycle: LifecycleValidator,
        conflict: ConflictDetector,
        gap: GapDetector,
        suspect: SuspectDetector,
        provenance: ProvenanceDetector,
    ) -> None:
        self._lifecycle = lifecycle
        self._conflict = conflict
        self._gap = gap
        self._suspect = suspect
        self._provenance = provenance

    async def run(
        self,
        candidates: list[ScoredArtifact],
        *,
        current_ref: str | None = None,
        workspace: WorkspacePort | None = None,
    ) -> ValidityResult:
        valid: list[Artifact] = []
        excluded: list[ExcludedArtifact] = []

        for scored in candidates:
            artifact = scored.artifact
            verdict = self._lifecycle.validate(
                artifact, current_ref=current_ref
            )
            if verdict.valid and workspace is not None:
                issue = await self._lifecycle.verify_engineering(
                    artifact, workspace
                )
                if issue is not None:
                    verdict = Verdict(artifact.id, False, [issue])
            if verdict.valid:
                valid.append(artifact)
            else:
                excluded.append(
                    ExcludedArtifact(
                        artifact=artifact, reasons=verdict.reasons
                    )
                )

        findings: list[Finding] = []
        findings.extend(await self._conflict.detect(valid))
        findings.extend(await self._provenance.detect(valid))
        findings.extend(await self._gap.detect(valid))
        findings.extend(await self._suspect.detect(valid))
        return ValidityResult(
            valid=valid, excluded=excluded, findings=findings
        )
