from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .entities import Artifact
from .enums import ArtifactType, LifecycleStatus


def byte_size(text: str) -> int:
    """UTF-8 byte size, the single budget accounting口径."""
    return len(text.encode("utf-8"))


def is_currently_effective(
    artifact: Artifact, now: datetime, ref: str | None = None
) -> bool:
    """State / time / scope validity (the engineering cross-check is added by the app layer)."""
    if artifact.status != LifecycleStatus.active:
        return False
    if artifact.effective_from and now < artifact.effective_from:
        return False
    if artifact.effective_to and now > artifact.effective_to:
        return False
    if ref and artifact.applies_to_ref and ref not in artifact.applies_to_ref:
        return False
    return True


def supersession_closure(
    artifact: Artifact, lookup: Callable[[str], Artifact | None]
) -> Artifact:
    """Follow superseded_by to the newest version (cycle-safe)."""
    current = artifact
    seen: set[str] = set()
    while current.superseded_by and current.id not in seen:
        seen.add(current.id)
        nxt = lookup(current.superseded_by)
        if nxt is None:
            break
        current = nxt
    return current


def expected_chain_complete(artifacts: list[Artifact]) -> list[ArtifactType]:
    """Return the missing artifact types along requirement->design->code->test."""
    present = {a.type for a in artifacts}
    missing: list[ArtifactType] = []
    for kind in (
        ArtifactType.requirement,
        ArtifactType.design,
        ArtifactType.code,
        ArtifactType.test,
    ):
        if kind not in present:
            missing.append(kind)
    return missing
