from __future__ import annotations

from datetime import datetime

from .entities import Artifact
from .enums import LifecycleStatus


def byte_size(text: str) -> int:
    """UTF-8 byte size, the single budget accounting口径."""
    return len(text.encode("utf-8"))


def effectiveness_reasons(
    artifact: Artifact, now: datetime, ref: str | None = None
) -> list[str]:
    """State / time / scope validity reasons (empty means currently effective).

    The engineering cross-check is added by the application layer.
    """
    reasons: list[str] = []
    if artifact.status != LifecycleStatus.active:
        reasons.append(f"status is {artifact.status}")
    if artifact.superseded_by:
        reasons.append(f"superseded by {artifact.superseded_by}")
    if artifact.effective_from and now < artifact.effective_from:
        reasons.append("not yet effective")
    if artifact.effective_to and now > artifact.effective_to:
        reasons.append("past effective_to")
    if ref and artifact.applies_to_ref and ref not in artifact.applies_to_ref:
        reasons.append(f"does not apply to ref {ref}")
    return reasons
