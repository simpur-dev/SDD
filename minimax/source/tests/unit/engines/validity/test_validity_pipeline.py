from __future__ import annotations

from datetime import datetime

from fakes.catalog import InMemoryCatalog
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.validity import (
    ConflictDetector,
    GapDetector,
    LifecycleValidator,
    ProvenanceDetector,
    SuspectDetector,
    ValidityEngine,
)
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import (
    ArtifactType,
    FindingKind,
    LifecycleStatus,
)
from specweaver.domain.ports.catalog import ScoredArtifact
from specweaver.domain.values import SourceRef

_NOW = datetime(2026, 9, 25)


def _engine(catalog: InMemoryCatalog) -> ValidityEngine:
    lifecycle = LifecycleValidator(now=lambda: _NOW)
    return ValidityEngine(
        lifecycle,
        ConflictDetector(),
        GapDetector(catalog),
        SuspectDetector(catalog),
        ProvenanceDetector(),
    )


async def test_pipeline_partitions_and_collects_findings() -> None:
    catalog = InMemoryCatalog()
    req = Artifact(
        id="REQ-1",
        project_id="p",
        type=ArtifactType.requirement,
        title="r1",
        content="# r\n- 应能调整发车时间",
    )
    old = Artifact(
        id="REQ-OLD",
        project_id="p",
        type=ArtifactType.requirement,
        title="old",
        status=LifecycleStatus.superseded,
    )
    tentative = Artifact(
        id="REQ-2",
        project_id="p",
        type=ArtifactType.requirement,
        title="r2",
        tags=["tentative"],
    )
    for artifact in (req, old, tentative):
        await catalog.upsert_artifact(artifact)

    candidates = [
        ScoredArtifact(artifact=req, score=1.0),
        ScoredArtifact(artifact=old, score=0.7),
        ScoredArtifact(artifact=tentative, score=0.6),
    ]
    result = await _engine(catalog).run(candidates)

    assert {a.id for a in result.valid} == {"REQ-1", "REQ-2"}
    assert [e.artifact.id for e in result.excluded] == ["REQ-OLD"]
    kinds = [f.kind for f in result.findings]
    assert kinds.count(FindingKind.gap) == 6
    assert kinds.count(FindingKind.unverified) == 1


async def test_pipeline_excludes_when_source_missing() -> None:
    catalog = InMemoryCatalog()
    code = Artifact(
        id="CODE-1",
        project_id="p",
        type=ArtifactType.code,
        title="c",
        source=SourceRef(uri="missing.py", checksum="abc"),
    )
    await catalog.upsert_artifact(code)
    result = await _engine(catalog).run(
        [ScoredArtifact(artifact=code, score=1.0)],
        workspace=InMemoryWorkspace({}),
    )
    assert [e.artifact.id for e in result.excluded] == ["CODE-1"]
    reasons = [r for e in result.excluded for r in e.reasons]
    assert any("no longer exists" in r for r in reasons)
