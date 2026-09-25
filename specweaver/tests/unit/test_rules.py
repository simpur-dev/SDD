from __future__ import annotations

from datetime import datetime, timedelta

from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType, LifecycleStatus
from specweaver.domain.rules import (
    byte_size,
    expected_chain_complete,
    is_currently_effective,
    supersession_closure,
)


def _art(**kwargs) -> Artifact:
    base = dict(id="a1", project_id="p", type=ArtifactType.requirement, title="t")
    base.update(kwargs)
    return Artifact(**base)


def test_byte_size() -> None:
    assert byte_size("a") == 1
    assert byte_size("中") == 3


def test_is_currently_effective() -> None:
    now = datetime(2026, 9, 25)
    assert is_currently_effective(_art(), now)
    assert not is_currently_effective(
        _art(status=LifecycleStatus.superseded), now
    )
    assert not is_currently_effective(
        _art(effective_from=now + timedelta(days=1)), now
    )
    assert not is_currently_effective(
        _art(effective_to=now - timedelta(days=1)), now
    )


def test_expected_chain_complete() -> None:
    gaps = expected_chain_complete([_art(type=ArtifactType.requirement)])
    assert ArtifactType.design in gaps
    assert ArtifactType.code in gaps
    assert ArtifactType.test in gaps

    full = [
        _art(id=t.value, type=t)
        for t in (
            ArtifactType.requirement,
            ArtifactType.design,
            ArtifactType.code,
            ArtifactType.test,
        )
    ]
    assert expected_chain_complete(full) == []


def test_supersession_closure() -> None:
    a1 = _art(id="a1", superseded_by="a2")
    a2 = _art(id="a2")
    lookup = {"a1": a1, "a2": a2}.get
    assert supersession_closure(a1, lookup).id == "a2"

    b1 = _art(id="b1", superseded_by="b2")
    b2 = _art(id="b2", superseded_by="b1")
    bmap = {"b1": b1, "b2": b2}.get
    assert supersession_closure(b1, bmap).id in {"b1", "b2"}
