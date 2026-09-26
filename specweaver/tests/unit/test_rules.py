from __future__ import annotations

from datetime import datetime, timedelta

from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType, LifecycleStatus
from specweaver.domain.rules import byte_size, effectiveness_reasons


def _art(**kwargs) -> Artifact:
    base = dict(id="a1", project_id="p", type=ArtifactType.requirement, title="t")
    base.update(kwargs)
    return Artifact(**base)


def test_byte_size() -> None:
    assert byte_size("a") == 1
    assert byte_size("中") == 3


def test_effective_artifact_has_no_reasons() -> None:
    now = datetime(2026, 9, 25)
    assert effectiveness_reasons(_art(), now) == []


def test_inactive_status_and_supersession_are_reported() -> None:
    now = datetime(2026, 9, 25)
    reasons = effectiveness_reasons(
        _art(status=LifecycleStatus.superseded, superseded_by="a2"), now
    )
    assert any("status" in r for r in reasons)
    assert any("superseded by a2" in r for r in reasons)


def test_time_window_is_respected() -> None:
    now = datetime(2026, 9, 25)
    assert effectiveness_reasons(
        _art(effective_from=now + timedelta(days=1)), now
    ) == ["not yet effective"]
    assert effectiveness_reasons(
        _art(effective_to=now - timedelta(days=1)), now
    ) == ["past effective_to"]


def test_ref_scope_is_respected() -> None:
    now = datetime(2026, 9, 25)
    assert effectiveness_reasons(
        _art(applies_to_ref="main"), now, ref="release-1"
    ) == ["does not apply to ref release-1"]
    assert (
        effectiveness_reasons(_art(applies_to_ref="main"), now, ref="main")
        == []
    )
