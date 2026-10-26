"""Driving-layer contract: MCP tools are thin wrappers over the usecases.

The in-process FastMCP client exercises the same serialisation path an Agent
sees, so argument plumbing, payload shape and the SWError -> ToolError
mapping are covered without touching the real backends.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fakes.memory import InMemoryMemory
from fastmcp import Client

from specweaver.adapters.driving.mcp.server import build_mcp
from specweaver.application.usecases.explain_source import (
    ExplainSourceReport,
    SourceNode,
)
from specweaver.application.usecases.record_decision import (
    RecordDecisionReport,
)
from specweaver.application.usecases.report_progress import (
    ReportProgressReport,
)
from specweaver.application.usecases.verify_state import VerifyStateReport
from specweaver.shared.config import Settings
from specweaver.shared.di import SpecWeaverApp
from specweaver.shared.errors import InvalidRequest, SWError
from specweaver.shared.telemetry import Telemetry

_TOOLS = {
    "sw_ping",
    "sw_doctor",
    "sw_ingest_project",
    "sw_get_context",
    "sw_complete_task",
    "sw_handoff",
    "sw_resume_task",
    "sw_record_decision",
    "sw_report_progress",
    "sw_verify",
    "sw_explain_source",
}


class _RecordingUseCase:
    """Stand-in for a usecase: captures the request, returns a preset."""

    def __init__(self, result: Any = None, error: SWError | None = None) -> None:
        self.result = result
        self.error = error
        self.requests: list[Any] = []

    async def __call__(self, request: Any) -> Any:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _app(**usecases: Any) -> SpecWeaverApp:
    return SpecWeaverApp(
        settings=Settings(),
        telemetry=Telemetry(),
        workspace=None,  # type: ignore[arg-type]
        test_runner=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        embedding=None,  # type: ignore[arg-type]
        pc_client=None,  # type: ignore[arg-type]
        memory=InMemoryMemory(),
        usecases=dict(usecases),
    )


async def _call(app: SpecWeaverApp, name: str, args: dict) -> Any:
    async with Client(build_mcp(app)) as client:
        result = await client.call_tool(name, args)
    return result


async def _payload(app: SpecWeaverApp, name: str, args: dict) -> dict:
    result = await _call(app, name, args)
    return json.loads(result.content[0].text)


async def test_every_delivered_usecase_has_a_tool() -> None:
    async with Client(build_mcp(_app())) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == _TOOLS


async def test_tool_annotations_declare_read_only_semantics() -> None:
    """Agents decide whether a retry is safe from these hints (docs/03 §7.2)."""
    async with Client(build_mcp(_app())) as client:
        hints = {
            tool.name: tool.annotations for tool in await client.list_tools()
        }

    assert all(
        hints[name].read_only_hint and hints[name].idempotent_hint
        for name in (
            "sw_ping",
            "sw_doctor",
            "sw_get_context",
            "sw_verify",
            "sw_explain_source",
        )
    )
    # replaying the ingestion upsert converges; replaying a handoff or a
    # decision does not (each call mints a new revision / entry)
    assert hints["sw_ingest_project"].read_only_hint is False
    assert hints["sw_ingest_project"].idempotent_hint is True
    for name in ("sw_handoff", "sw_record_decision", "sw_report_progress",
                 "sw_complete_task", "sw_resume_task"):
        assert hints[name].read_only_hint is False
        assert hints[name].idempotent_hint is False
    assert all(h.destructive_hint is False for h in hints.values())
    assert set(hints) == _TOOLS


async def test_sw_record_decision_forwards_the_resolved_scope() -> None:
    usecase = _RecordingUseCase(
        RecordDecisionReport(action="remembered", entry_id="mem-1")
    )
    payload = await _payload(
        _app(record_decision=usecase),
        "sw_record_decision",
        {"project_id": "railway", "decision": "用 seekdb 存目录"},
    )

    assert payload == {
        "action": "remembered",
        "entry_id": "mem-1",
        "revision": "",
    }
    (request,) = usecase.requests
    assert request.scope_id == "scp-railway"
    assert request.decision == "用 seekdb 存目录"


async def test_sw_record_decision_revises_and_retires_by_entry_id() -> None:
    usecase = _RecordingUseCase(
        RecordDecisionReport(action="revised", entry_id="mem-1")
    )
    await _payload(
        _app(record_decision=usecase),
        "sw_record_decision",
        {
            "project_id": "railway",
            "decision": "改选方案",
            "replaces_entry_id": "mem-1",
            "scope_id": "scp-keep",
        },
    )
    (request,) = usecase.requests
    assert request.replaces_entry_id == "mem-1"
    assert request.scope_id == "scp-keep"  # caller-provided scope wins


async def test_sw_report_progress_can_snapshot_a_handoff() -> None:
    usecase = _RecordingUseCase(
        ReportProgressReport(entry_id="mem-2", handoff_rev="rev-9")
    )
    payload = await _payload(
        _app(report_progress=usecase),
        "sw_report_progress",
        {
            "project_id": "railway",
            "note": "索引已重建",
            "next_steps": ["核对上下文"],
            "update_handoff": True,
        },
    )

    assert payload == {"entry_id": "mem-2", "handoff_rev": "rev-9"}
    (request,) = usecase.requests
    assert request.update_handoff is True
    assert request.next_steps == ["核对上下文"]


async def test_sw_verify_reports_the_three_way_check() -> None:
    usecase = _RecordingUseCase(
        VerifyStateReport(
            project_id="railway",
            checked=12,
            current_ref="abc123",
            rules_in_catalog=3,
            constraint_entries_in_memory=2,
            notes=["stale change set"],
        )
    )
    payload = await _payload(
        _app(verify_state=usecase),
        "sw_verify",
        {"project_id": "railway"},
    )

    assert payload["checked"] == 12
    assert payload["test_report"] == "absent"
    assert payload["mismatches"] == []
    assert payload["notes"] == ["stale change set"]
    (request,) = usecase.requests
    assert request.scope_id == "scp-railway"


async def test_sw_verify_degrades_when_the_scope_cannot_resolve() -> None:
    class _DownMemory(InMemoryMemory):
        async def resolve_scope(self, project_id: str) -> str:
            raise SWError("powercontext unreachable")

    app = _app(
        verify_state=_RecordingUseCase(
            VerifyStateReport(project_id="railway", checked=4)
        ),
    )
    app.memory = _DownMemory()
    payload = await _payload(
        app, "sw_verify", {"project_id": "railway"}
    )

    assert payload["checked"] == 4
    assert payload["notes"][0].startswith("scope unresolved: [SW-ERROR]")
    (request,) = app.usecases["verify_state"].requests
    assert request.scope_id == ""


async def test_sw_explain_source_returns_the_citation_chain() -> None:
    usecase = _RecordingUseCase(
        ExplainSourceReport(
            root=SourceNode(
                id="CODE-1", type="code", status="active", version="1"
            ),
            upstream=[
                SourceNode(
                    id="REQ-1", type="requirement", status="active", version="2"
                )
            ],
            missing_refs=["REQ-404"],
        )
    )
    payload = await _payload(
        _app(explain_source=usecase),
        "sw_explain_source",
        {"project_id": "railway", "artifact_id": "CODE-1", "depth": 2},
    )

    assert payload["root"]["id"] == "CODE-1"
    assert payload["upstream"][0]["id"] == "REQ-1"
    assert payload["missing_refs"] == ["REQ-404"]
    (request,) = usecase.requests
    assert (request.artifact_id, request.depth) == ("CODE-1", 2)


@pytest.mark.parametrize(
    ("tool", "args", "usecase"),
    [
        (
            "sw_record_decision",
            {"project_id": "railway", "decision": "d"},
            "record_decision",
        ),
        (
            "sw_report_progress",
            {"project_id": "railway", "note": "n"},
            "report_progress",
        ),
        (
            "sw_verify",
            {"project_id": "railway"},
            "verify_state",
        ),
        (
            "sw_explain_source",
            {"project_id": "railway", "artifact_id": "REQ-1"},
            "explain_source",
        ),
    ],
)
async def test_backend_errors_surface_as_tool_errors(
    tool: str, args: dict, usecase: str
) -> None:
    app = _app(
        **{
            usecase: _RecordingUseCase(
                error=InvalidRequest("backend said no")
            )
        }
    )
    with pytest.raises(Exception) as excinfo:
        await _call(app, tool, args)
    assert "[SW-INVALID] backend said no" in str(excinfo.value)
