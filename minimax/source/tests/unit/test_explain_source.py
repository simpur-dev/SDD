from __future__ import annotations

import pytest
from fakes.catalog import InMemoryCatalog

from specweaver.application.usecases.explain_source import (
    ExplainSource,
    ExplainSourceRequest,
)
from specweaver.domain.entities import Artifact, Relation
from specweaver.domain.enums import ArtifactType, RelationKind
from specweaver.domain.values import SourceRef
from specweaver.shared.errors import SWError
from specweaver.shared.telemetry import Telemetry


async def _seed() -> InMemoryCatalog:
    catalog = InMemoryCatalog()
    req = Artifact(
        id="REQ-1",
        project_id="railway",
        type=ArtifactType.requirement,
        title="按站调整",
        source=SourceRef(uri="specs/req.md", checksum="sha256:r"),
    )
    des = Artifact(
        id="DES-1",
        project_id="railway",
        type=ArtifactType.design,
        module="schedule",
        title="时刻设计",
        based_on=["REQ-1"],
        source=SourceRef(uri="design/d.md", checksum="sha256:d"),
    )
    code = Artifact(
        id="CODE-1",
        project_id="railway",
        type=ArtifactType.code,
        module="schedule",
        title="schedule",
        based_on=["DES-1", "REQ-404"],
        source=SourceRef(uri="src/schedule.py", checksum="sha256:c"),
    )
    for artifact in (req, des, code):
        await catalog.upsert_artifact(artifact)
    await catalog.upsert_relation(
        Relation(
            project_id="railway", src="DES-1", dst="REQ-1",
            kind=RelationKind.realizes,
        )
    )
    await catalog.upsert_relation(
        Relation(
            project_id="railway", src="CODE-1", dst="DES-1",
            kind=RelationKind.realizes,
        )
    )
    return catalog


async def test_explain_depth_one() -> None:
    usecase = ExplainSource(await _seed(), Telemetry())
    report = await usecase(
        ExplainSourceRequest(
            project_id="railway", artifact_id="CODE-1", depth=1
        )
    )
    assert report.root.source_uri == "src/schedule.py"
    assert [n.id for n in report.upstream] == ["DES-1"]
    assert report.missing_refs == ["REQ-404"]
    # DES-1 was already surfaced as upstream, so it is not repeated below
    assert report.downstream == []


async def test_explain_from_requirement_shows_downstream() -> None:
    usecase = ExplainSource(await _seed(), Telemetry())
    report = await usecase(
        ExplainSourceRequest(
            project_id="railway", artifact_id="REQ-1", depth=2
        )
    )
    assert {n.id for n in report.downstream} == {"DES-1", "CODE-1"}
    assert report.upstream == []


async def test_explain_recursive_upstream() -> None:
    usecase = ExplainSource(await _seed(), Telemetry())
    report = await usecase(
        ExplainSourceRequest(
            project_id="railway", artifact_id="CODE-1", depth=2
        )
    )
    assert [n.id for n in report.upstream] == ["DES-1", "REQ-1"]
    assert report.upstream[1].source_uri == "specs/req.md"


async def test_explain_unknown_and_degraded() -> None:
    usecase = ExplainSource(await _seed(), Telemetry())
    with pytest.raises(SWError):
        await usecase(
            ExplainSourceRequest(project_id="railway", artifact_id="NOPE")
        )
    degraded = ExplainSource(None, Telemetry())
    with pytest.raises(SWError):
        await degraded(
            ExplainSourceRequest(project_id="p", artifact_id="X")
        )
