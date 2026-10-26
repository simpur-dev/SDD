from __future__ import annotations

from fakes.catalog import InMemoryCatalog

from specweaver.application.engines.validity import GapDetector
from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import (
    ArtifactType,
    RelationKind,
)


def _artifact(artifact_id: str, artifact_type: ArtifactType) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=artifact_type,
        title=artifact_id,
    )


async def test_all_layers_missing() -> None:
    catalog = InMemoryCatalog()
    req = _artifact("REQ-1", ArtifactType.requirement)
    await catalog.upsert_artifact(req)
    findings = await GapDetector(catalog).detect([req])
    assert len(findings) == 3
    messages = " ".join(f.message for f in findings)
    assert "design" in messages
    assert "code" in messages
    assert "test" in messages


async def test_orphan_requirement_outside_candidates_still_reported() -> None:
    """LLM narrowing can miss orphan specs; completeness covers the project."""
    catalog = InMemoryCatalog()
    orphan = _artifact("REQ-5", ArtifactType.requirement)
    await catalog.upsert_artifact(orphan)
    other = _artifact("DES-1", ArtifactType.design)
    findings = await GapDetector(catalog).detect([other])
    assert len(findings) == 3
    assert {f.refs[0].artifact_id for f in findings} == {"REQ-5"}


async def test_complete_chain_has_no_gap() -> None:
    catalog = InMemoryCatalog()
    req = _artifact("REQ-1", ArtifactType.requirement)
    design = _artifact("DES-1", ArtifactType.design)
    code = _artifact("CODE-1", ArtifactType.code)
    test = _artifact("TST-1", ArtifactType.test)
    for artifact in (req, design, code, test):
        await catalog.upsert_artifact(artifact)
    await catalog.upsert_relation(
        Relation(
            project_id="p",
            src=design.id,
            dst=req.id,
            kind=RelationKind.realizes,
        )
    )
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
    findings = await GapDetector(catalog).detect([req])
    assert findings == []
