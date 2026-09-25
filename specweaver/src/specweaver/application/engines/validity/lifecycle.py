from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ....domain.entities import Artifact
from ....domain.enums import LifecycleStatus
from ....domain.ports.workspace import WorkspacePort


@dataclass
class Verdict:
    artifact_id: str
    valid: bool
    reasons: list[str] = field(default_factory=list)


class LifecycleValidator:
    """Four-dimensional validity: status, time, scope and (optionally) engineering."""

    def __init__(self, now=None) -> None:
        self._now = now or datetime.now

    def validate(
        self, artifact: Artifact, *, current_ref: str | None = None
    ) -> Verdict:
        reasons: list[str] = []

        if artifact.status != LifecycleStatus.active:
            reasons.append(f"status is {artifact.status}")
        if artifact.superseded_by:
            reasons.append(f"superseded by {artifact.superseded_by}")

        now = self._now()
        if artifact.effective_from and now < artifact.effective_from:
            reasons.append("not yet effective")
        if artifact.effective_to and now > artifact.effective_to:
            reasons.append("past effective_to")

        if (
            current_ref
            and artifact.applies_to_ref
            and current_ref not in artifact.applies_to_ref
        ):
            reasons.append(f"does not apply to ref {current_ref}")

        return Verdict(artifact.id, not reasons, reasons)

    async def verify_engineering(
        self, artifact: Artifact, workspace: WorkspacePort
    ) -> str | None:
        if artifact.source is None or not artifact.source.uri:
            return None
        uri = artifact.source.uri
        if not await workspace.exists(uri):
            return f"source file {uri} no longer exists"
        if artifact.source.checksum:
            actual = await workspace.checksum(uri)
            if actual != artifact.source.checksum:
                return "source checksum does not match the recorded artifact"
        return None
