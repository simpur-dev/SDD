"""Repository-profile resolution and its wiring through IngestProject."""

from __future__ import annotations

import copy

import pytest
from fakes.catalog import InMemoryCatalog
from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.ingestion import IngestionEngine
from specweaver.application.engines.ingestion.profiles import (
    known_profiles,
    resolve_profile,
)
from specweaver.application.usecases.ingest_project import (
    IngestProject,
    IngestProjectRequest,
)
from specweaver.shared.errors import InvalidRequest
from specweaver.shared.telemetry import Telemetry

FILES = {
    "specs/req.md": "---\nid: REQ-1\n---\n# 需求\n",
    "src/schedule.py": '"""调度。"""\n\n\nclass Schedule:\n    pass\n',
}


async def test_known_profiles_and_explicit_resolution() -> None:
    assert "specweaver" in known_profiles()
    assert "plain" in known_profiles()
    assert "auto" in known_profiles()
    workspace = InMemoryWorkspace(copy.deepcopy(FILES))
    profile = await resolve_profile(workspace, requested="plain")
    assert profile.name == "plain"
    profile = await resolve_profile(workspace, requested="specweaver")
    assert profile.name == "specweaver"


async def test_unknown_profile_is_invalid_request() -> None:
    workspace = InMemoryWorkspace({})
    with pytest.raises(InvalidRequest) as excinfo:
        await resolve_profile(workspace, requested="nosuch")
    assert "nosuch" in str(excinfo.value)
    assert "specweaver" in str(excinfo.value)  # known names are listed


async def test_request_beats_configured_setting() -> None:
    workspace = InMemoryWorkspace({})
    profile = await resolve_profile(
        workspace, requested="plain", configured="specweaver"
    )
    assert profile.name == "plain"


async def test_configured_setting_beats_sniffing() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES))  # has specs/ marker
    profile = await resolve_profile(
        workspace, requested="", configured="plain"
    )
    assert profile.name == "plain"


async def test_auto_sniff_falls_back_to_default() -> None:
    # v1 registers only the default convention's markers, so auto resolves to
    # specweaver both when markers match and when nothing matches.
    workspace = InMemoryWorkspace({})
    profile = await resolve_profile(workspace, requested="", configured="auto")
    assert profile.name == "specweaver"


def _usecase(workspace, **kwargs):
    engine = IngestionEngine(ScriptedEmbedding(dim=8))
    return IngestProject(
        engine,
        InMemoryCatalog(),
        workspace,
        Telemetry(),
        default_profile=kwargs.pop("default_profile", "auto"),
        **kwargs,
    )


async def test_report_echoes_resolved_profile() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES))
    report = await _usecase(workspace)(
        IngestProjectRequest(project_id="railway")
    )
    assert report.profile == "specweaver"  # auto -> default convention


async def test_request_profile_reaches_the_run() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES))
    report = await _usecase(workspace)(
        IngestProjectRequest(project_id="railway", profile="plain")
    )
    assert report.profile == "plain"


async def test_default_profile_setting_applies_when_request_empty() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(FILES))
    report = await _usecase(workspace, default_profile="plain")(
        IngestProjectRequest(project_id="railway")
    )
    assert report.profile == "plain"
