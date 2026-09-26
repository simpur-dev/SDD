from __future__ import annotations

import copy

from fakes.catalog import InMemoryCatalog
from fakes.inference import ScriptedEmbedding
from fakes.memory import InMemoryMemory
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.ingestion import IngestionEngine
from specweaver.application.usecases.ingest_project import (
    IngestProject,
    IngestProjectRequest,
)
from specweaver.shared.telemetry import Telemetry

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


def _usecase(catalog, memory, workspace):
    engine = IngestionEngine(ScriptedEmbedding(dim=8))
    return IngestProject(
        engine, catalog, workspace, Telemetry(), memory
    )


async def test_ingest_persists_and_registers_source() -> None:
    catalog = InMemoryCatalog()
    memory = InMemoryMemory()
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")

    report = await _usecase(catalog, memory, workspace)(
        IngestProjectRequest(project_id="railway", scope_id="scp-1")
    )

    assert report.added == 4
    assert report.relations >= 4
    assert report.source_registered
    assert len(catalog.artifacts) == 4
    assert len(memory.entries) == 1
    assert memory.entries[0].kind == "ingestion"


async def test_second_ingest_is_incremental() -> None:
    catalog = InMemoryCatalog()
    memory = InMemoryMemory()
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")
    usecase = _usecase(catalog, memory, workspace)

    await usecase(
        IngestProjectRequest(project_id="railway", scope_id="scp-1")
    )
    report = await usecase(
        IngestProjectRequest(project_id="railway", scope_id="scp-1")
    )
    assert report.added == 0
    assert report.unchanged == 4


async def test_ingest_without_scope_skips_source_registration() -> None:
    catalog = InMemoryCatalog()
    memory = InMemoryMemory()
    workspace = InMemoryWorkspace(copy.deepcopy(FILES), ref="abc123")

    report = await _usecase(catalog, memory, workspace)(
        IngestProjectRequest(project_id="railway")
    )

    assert len(catalog.artifacts) == 4
    assert report.source_registered is False
    assert memory.entries == []
