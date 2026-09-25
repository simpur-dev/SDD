from __future__ import annotations

from fakes.catalog import InMemoryCatalog

from specweaver.application.engines.validity import SuspectDetector
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import (
    ArtifactType,
    FindingKind,
    LifecycleStatus,
)


def _artifact(artifact_id: str, artifact_type, **overrides) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=artifact_type,
        title=artifact_id,
        **overrides,
    )


async def test_based_on_superseded_is_suspect() -> None:
    catalog = InMemoryCatalog()
    design = _artifact(
        "DES-1", ArtifactType.design, status=LifecycleStatus.superseded
    )
    code = _artifact(
        "CODE-1", ArtifactType.code, based_on=["DES-1"]
    )
    for artifact in (design, code):
        await catalog.upsert_artifact(artifact)
    findings = await SuspectDetector(catalog).detect([code])
    assert len(findings) == 1
    assert findings[0].kind is FindingKind.suspect


async def test_based_on_active_is_not_flagged() -> None:
    catalog = InMemoryCatalog()
    design = _artifact("DES-1", ArtifactType.design)
    code = _artifact(
        "CODE-1", ArtifactType.code, based_on=["DES-1"]
    )
    for artifact in (design, code):
        await catalog.upsert_artifact(artifact)
    assert await SuspectDetector(catalog).detect([code]) == []
