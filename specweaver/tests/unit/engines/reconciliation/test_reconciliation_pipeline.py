from __future__ import annotations

from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.reconciliation import (
    ReconciliationEngine,
)
from specweaver.domain.entities import Artifact, FileChange
from specweaver.domain.enums import ArtifactType, LifecycleStatus


async def test_reconcile_rebuilds_modified_code() -> None:
    files = {
        "src/schedule.py": (
            "def adjust_departure(station):\n    return station\n"
        )
    }
    changes = [FileChange(path="src/schedule.py", change_type="modified")]
    workspace = InMemoryWorkspace(files, ref="head1", changes=changes)
    engine = ReconciliationEngine(ScriptedEmbedding(8))

    result = await engine.run(
        "railway", "task-1", workspace, "base1", "head1", {}, "cs-1"
    )

    assert result.change_set.id == "cs-1"
    assert result.change_set.base_checksum == "base1"
    assert len(result.change_set.files_changed) == 1
    assert len(result.updated) == 1
    artifact = result.updated[0]
    assert artifact.type == ArtifactType.code
    assert artifact.checksum
    assert artifact.embedding
    assert result.superseded == []


async def test_reconcile_marks_explicit_supersede() -> None:
    content = (
        "---\n"
        "type: requirement\n"
        "id: REQ-02\n"
        "supersedes: REQ-01\n"
        "module: schedule\n"
        "---\n\n"
        "# 需求 v2\n\n"
        "- 新要求\n"
    )
    files = {"specs/requirement-v2.md": content}
    changes = [
        FileChange(path="specs/requirement-v2.md", change_type="added")
    ]
    workspace = InMemoryWorkspace(files, ref="head2", changes=changes)
    old = Artifact(
        id="REQ-1",
        project_id="railway",
        type=ArtifactType.requirement,
        title="old",
        status=LifecycleStatus.active,
    )
    engine = ReconciliationEngine(ScriptedEmbedding(8))

    result = await engine.run(
        "railway",
        "task-1",
        workspace,
        "base1",
        "head2",
        {"REQ-1": old},
        "cs-2",
    )

    assert result.updated[0].id == "REQ-2"
    assert len(result.superseded) == 1
    superseded = result.superseded[0]
    assert superseded.id == "REQ-1"
    assert superseded.status == LifecycleStatus.superseded
    assert superseded.superseded_by == "REQ-2"
