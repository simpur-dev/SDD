"""The CLI is a delivered driving adapter: its option surface and exit codes
are the contract an Agent or CI depends on, so they are tested, not assumed.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

from specweaver.adapters.driving.cli import app as cli
from specweaver.domain.entities import Artifact, ContextBundle, Task
from specweaver.domain.enums import ArtifactType
from specweaver.domain.values import Budget
from specweaver.shared import di
from specweaver.shared.errors import SWError

runner = CliRunner()

# what specweaver/README.md claims about the option surface
JSON_COMMANDS = ["doctor", "ingest", "context", "finish", "handoff", "resume"]
USAGE_COMMANDS = ["ingest", "context", "finish", "handoff", "resume"]


class _IngestReport(BaseModel):
    project_id: str = "p"
    added: int = 1
    updated: int = 2
    unchanged: int = 3
    skipped: int = 0
    relations: int = 4
    deprecated: int = 0
    duplicate_ids: list[str] = []
    source_registered: bool = True


class _Telemetry:
    def __init__(self, fail_with: OSError | None = None) -> None:
        self.paths: list[str] = []
        self._fail_with = fail_with

    def to_csv(self, path: str) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.paths.append(path)


class _App:
    def __init__(self, usecase=None, doctor=None, telemetry=None) -> None:
        self.usecases = {"ingest_project": usecase or _default_ingest}
        self._doctor = doctor or {
            "seekdb": {"ok": True},
            "powercontext": {"ok": True},
            "inference": {"provider": "qianwen"},
        }
        self.telemetry = telemetry or _Telemetry()

    async def doctor(self) -> dict:
        return self._doctor

    async def ensure_scope(self, project_id: str, scope_id: str = "") -> str:
        return scope_id or "scp-1"


async def _default_ingest(request) -> _IngestReport:
    return _IngestReport(project_id=request.project_id)


def _patch(monkeypatch, app: _App) -> _App:
    @asynccontextmanager
    async def _run(settings):  # mirrors di.run's async-context-manager contract
        yield app

    monkeypatch.setattr(di, "run", _run)
    return app


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_documented_commands_advertise_the_json_option(command: str) -> None:
    result = runner.invoke(cli.app, [command, "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output


@pytest.mark.parametrize("command", USAGE_COMMANDS)
def test_documented_commands_advertise_the_usage_out_option(command: str) -> None:
    result = runner.invoke(cli.app, [command, "--help"])
    assert result.exit_code == 0
    assert "--usage-out" in result.output


def test_version_reports_a_release_and_exits_zero() -> None:
    result = runner.invoke(cli.app, ["version"])
    assert result.exit_code == 0
    assert any(char.isdigit() for char in result.output)


def test_doctor_json_is_machine_readable(monkeypatch) -> None:
    _patch(monkeypatch, _App())
    result = runner.invoke(cli.app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["ok"] is True
    assert payload["inference_provider"] == "qianwen"


def test_doctor_exits_one_when_a_backend_is_down(monkeypatch) -> None:
    _patch(
        monkeypatch,
        _App(
            doctor={
                "seekdb": {"ok": False, "error": "unreachable"},
                "powercontext": {"ok": True},
                "inference": {"provider": "none"},
            }
        ),
    )
    result = runner.invoke(cli.app, ["doctor"])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_ingest_json_carries_the_report(monkeypatch) -> None:
    app = _patch(monkeypatch, _App(telemetry=_Telemetry()))
    result = runner.invoke(
        cli.app, ["ingest", "railway", "--json", "--usage-out", "u.csv"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["project_id"] == "railway"
    assert app.telemetry.paths == ["u.csv"]


def test_sw_error_becomes_exit_code_two(monkeypatch) -> None:
    async def _boom(request):
        raise SWError("workspace not readable")

    _patch(monkeypatch, _App(usecase=_boom))
    result = runner.invoke(cli.app, ["ingest", "railway"])
    assert result.exit_code == 2
    assert "workspace not readable" in result.stdout


def test_unwritable_usage_out_becomes_exit_code_three(monkeypatch) -> None:
    telemetry = _Telemetry(fail_with=OSError("disk full"))
    _patch(monkeypatch, _App(telemetry=telemetry))
    result = runner.invoke(
        cli.app, ["ingest", "railway", "--usage-out", "nope/u.csv"]
    )
    assert result.exit_code == 3
    assert "cannot write --usage-out" in result.stdout


class _Excluded:
    def __init__(self, artifact, reasons: list[str]) -> None:
        self.artifact = artifact
        self.reasons = reasons


class _ContextResult:
    def __init__(self, bundle, markdown, excluded, memory_error) -> None:
        self.bundle = bundle
        self.markdown = markdown
        self.excluded = excluded
        self.memory_error = memory_error


def _context_result():
    stale = Artifact(
        id="REQ-1",
        project_id="p",
        type=ArtifactType.requirement,
        title="发车时间需求",
        content="旧版本",
    )
    bundle = ContextBundle(
        task=Task(id="task-1", project_id="p", title="任务"),
        budget=Budget(max_bytes=8000, used_bytes=801, truncated=False),
    )
    return _ContextResult(
        bundle,
        "# Context: 任务\n\n## ① Current goal and effective constraints\n",
        [_Excluded(stale, ["checksum_mismatch"])],
        "powercontext 503 on POST /v1/memory/search",
    )


def _patch_context(monkeypatch) -> None:
    app = _App()

    async def _get_context(request):
        return _context_result()

    app.usecases["get_context"] = _get_context
    _patch(monkeypatch, app)


def test_context_json_reports_what_was_excluded(monkeypatch) -> None:
    _patch_context(monkeypatch)
    result = runner.invoke(cli.app, ["context", "p", "任务", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout[result.stdout.index("{") :])
    assert payload["excluded"] == [
        {"id": "REQ-1", "reasons": ["checksum_mismatch"]}
    ]
    assert "503" in payload["memory_error"]


def test_context_human_output_names_the_exclusion_reason(monkeypatch) -> None:
    _patch_context(monkeypatch)
    result = runner.invoke(cli.app, ["context", "p", "任务"])
    assert result.exit_code == 0
    assert "checksum_mismatch" in result.stdout
    assert "re-ingest" in result.stdout
    assert "working memory unavailable" in result.stdout
