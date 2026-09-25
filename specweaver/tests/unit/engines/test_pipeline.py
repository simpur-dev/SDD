from __future__ import annotations

import copy

from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.ingestion import IngestionEngine

FILES = {
    "specs/req.md": "---\nid: REQ-1\n---\n# 需求\n",
    "railway/schedule.py": (
        '"""调度。"""\nfrom occupancy import Occupancy\n\n\n'
        'class Schedule:\n    """@implements REQ-1"""\n    pass\n'
    ),
    "railway/occupancy.py": '"""占用。"""\n\n\nclass Occupancy:\n    pass\n',
    "tests/test_schedule.py": (
        'def test_schedule_adjust():\n    """@covers REQ-1"""\n    pass\n'
    ),
}


def _engine() -> IngestionEngine:
    return IngestionEngine(ScriptedEmbedding(dim=8))


async def test_first_ingest_indexes_everything() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")
    result = await _engine().run("railway", workspace, {})

    assert result.added == 4
    assert result.updated == 0
    assert result.unchanged == 0
    assert result.skipped == 0
    assert len(result.changed_ids) == 4
    assert len(result.relations) >= 4
    assert all(a.embedding is not None for a in result.artifacts)


async def test_second_ingest_is_fully_incremental() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")
    engine = _engine()
    first = await engine.run("railway", workspace, {})
    existing = {a.id: a.checksum for a in first.artifacts}

    second = await engine.run("railway", workspace, existing)
    assert second.added == 0
    assert second.updated == 0
    assert second.unchanged == 4
    assert second.changed_ids == []


async def test_modified_file_is_reindexed() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")
    engine = _engine()
    first = await engine.run("railway", workspace, {})
    existing = {a.id: a.checksum for a in first.artifacts}

    workspace.files["railway/schedule.py"] += "\n# changed line\n"
    third = await engine.run("railway", workspace, existing)
    assert third.updated == 1
    assert third.added == 0
    assert third.unchanged == 3
    assert len(third.changed_ids) == 1
