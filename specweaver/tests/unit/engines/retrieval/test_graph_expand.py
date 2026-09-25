from __future__ import annotations

from fakes.catalog import InMemoryCatalog

from specweaver.application.engines.retrieval import GraphExpander
from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import (
    ArtifactType,
    RelationKind,
)
from specweaver.domain.ports.catalog import ScoredArtifact


def _artifact(artifact_id: str, artifact_type: ArtifactType) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=artifact_type,
        title=artifact_id,
    )


async def _catalog() -> InMemoryCatalog:
    catalog = InMemoryCatalog()
    req = _artifact("REQ-1", ArtifactType.requirement)
    code = _artifact("CODE-1", ArtifactType.code)
    test = _artifact("TST-1", ArtifactType.test)
    for artifact in (req, code, test):
        await catalog.upsert_artifact(artifact)
    await catalog.upsert_relation(
        Relation(
            project_id="p",
            src=code.id,
            dst=req.id,
            kind=RelationKind.realizes,
        )
    )
    await catalog.upsert_relation(
        Relation(
            project_id="p",
            src=test.id,
            dst=code.id,
            kind=RelationKind.tests,
        )
    )
    return catalog


async def test_expand_depth_one_reaches_direct_peers() -> None:
    catalog = await _catalog()
    seed = ScoredArtifact(
        artifact=_artifact("REQ-1", ArtifactType.requirement), score=1.0
    )
    out = await GraphExpander(catalog, depth=1).expand([seed])
    ids = {s.artifact.id for s in out}
    assert "CODE-1" in ids
    assert "TST-1" not in ids


async def test_expand_depth_two_completes_chain() -> None:
    catalog = await _catalog()
    seed = ScoredArtifact(
        artifact=_artifact("REQ-1", ArtifactType.requirement), score=1.0
    )
    out = await GraphExpander(catalog, depth=2).expand([seed])
    ids = {s.artifact.id for s in out}
    assert {"CODE-1", "TST-1"} <= ids
