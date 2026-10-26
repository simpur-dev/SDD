from __future__ import annotations

from datetime import datetime

from specweaver.application.engines.validity import LifecycleValidator
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import (
    ArtifactType,
    LifecycleStatus,
)

_NOW = datetime(2026, 9, 25, 12, 0, 0)


def _artifact(**overrides) -> Artifact:
    return Artifact(
        id="x",
        project_id="p",
        type=ArtifactType.requirement,
        title="t",
        **overrides,
    )


def _validate(artifact, current_ref=None):
    return LifecycleValidator(now=lambda: _NOW).validate(
        artifact, current_ref=current_ref
    )


def test_active_artifact_is_valid() -> None:
    assert _validate(_artifact()).valid


def test_non_active_status_fails() -> None:
    verdict = _validate(_artifact(status=LifecycleStatus.superseded))
    assert not verdict.valid
    assert any("status" in reason for reason in verdict.reasons)


def test_superseded_by_fails() -> None:
    verdict = _validate(_artifact(superseded_by="REQ-2"))
    assert not verdict.valid
    assert any("superseded" in reason for reason in verdict.reasons)


def test_not_yet_effective_and_expired_fail() -> None:
    future = _artifact(effective_from=datetime(2027, 1, 1))
    assert not _validate(future).valid
    expired = _artifact(effective_to=datetime(2025, 1, 1))
    assert not _validate(expired).valid


def test_scope_ref_filtering() -> None:
    artifact = _artifact(applies_to_ref="release-2")
    assert not _validate(artifact, current_ref="release-1").valid
    assert _validate(artifact, current_ref="release-2").valid
