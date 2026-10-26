from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ....domain.entities import Artifact
from ....domain.ports.workspace import WorkspacePort
from ....domain.rules import effectiveness_reasons


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
        reasons = effectiveness_reasons(artifact, self._now(), current_ref)
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
