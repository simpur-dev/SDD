from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ....application.usecases.complete_task import CompleteTaskRequest
from ....application.usecases.create_handoff import CreateHandoffRequest
from ....application.usecases.explain_source import ExplainSourceRequest
from ....application.usecases.get_context import GetContextRequest
from ....application.usecases.ingest_project import IngestProjectRequest
from ....application.usecases.record_decision import RecordDecisionRequest
from ....application.usecases.report_progress import ReportProgressRequest
from ....application.usecases.resume_task import ResumeTaskRequest
from ....application.usecases.verify_state import VerifyStateRequest
from ....shared.errors import SWError

if TYPE_CHECKING:
    from ....shared.di import SpecWeaverApp


def _payload(result: Any) -> dict:
    return result.model_dump(mode="json")


def _as_tool_error(exc: SWError) -> ToolError:
    return ToolError(f"[{exc.code}] {exc.message}")


def build_mcp(app: SpecWeaverApp) -> FastMCP:
    mcp = FastMCP("SpecWeaver")

    async def _invoke(name: str, request: Any) -> Any:
        usecase = app.usecases[name]
        try:
            return await usecase(request)
        except SWError as exc:
            raise _as_tool_error(exc) from exc

    async def _scope(project_id: str, scope_id: str) -> str:
        """Resolve the PowerContext scope under the same error contract."""
        try:
            return await app.ensure_scope(project_id, scope_id)
        except SWError as exc:
            raise _as_tool_error(exc) from exc

    @mcp.tool
    async def sw_ping() -> str:
        """Liveness probe."""
        return "pong"

    @mcp.tool
    async def sw_doctor() -> dict:
        """Report seekdb / PowerContext connectivity and inference mode."""
        return await app.doctor()

    @mcp.tool
    async def sw_ingest_project(
        project_id: str,
        scope_id: str = "",
        register_source: bool = True,
    ) -> dict:
        """Ingest the real workspace into the seekdb catalog.

        Registers an ingestion note in PowerContext memory when
        ``register_source`` is set (scope resolved from project if empty).
        """
        if register_source:
            scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "ingest_project",
            IngestProjectRequest(
                project_id=project_id,
                scope_id=scope_id,
                register_source=register_source,
            ),
        )
        return _payload(report)

    @mcp.tool
    async def sw_get_context(
        project_id: str,
        task_text: str,
        base_ref: str = "",
    ) -> dict:
        """Assemble a budgeted Context Bundle (markdown) for a task."""
        result = await _invoke(
            "get_context",
            GetContextRequest(
                project_id=project_id,
                task_text=task_text,
                base_ref=base_ref or None,
            ),
        )
        bundle = result.bundle
        return {
            "markdown": result.markdown,
            "cited": [c.artifact_id for c in bundle.citations],
            "budget": bundle.budget.model_dump()
            if bundle.budget
            else None,
            "excluded": [
                {"id": e.artifact.id, "reasons": e.reasons}
                for e in result.excluded
            ],
        }

    @mcp.tool
    async def sw_complete_task(
        project_id: str,
        task_id: str,
        base_ref: str,
        scope_id: str = "",
        test_command: str = "pytest",
        register_outcome: bool = True,
    ) -> dict:
        """Run tests, reconcile artifacts on success, record change set/outcome."""
        if register_outcome:
            scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "complete_task",
            CompleteTaskRequest(
                project_id=project_id,
                task_id=task_id,
                base_ref=base_ref,
                scope_id=scope_id,
                test_command=test_command,
                register_outcome=register_outcome,
            ),
        )
        return _payload(report)

    @mcp.tool
    async def sw_handoff(
        project_id: str,
        objective: str = "",
        state: list[str] | None = None,
        next_steps: list[str] | None = None,
        omissions: list[str] | None = None,
        scope_id: str = "",
    ) -> dict:
        """Commit a handoff snapshot of the current task state.

        ``state`` needs at least one completed claim (PowerContext
        contract); ``next_steps`` the planned work, ``omissions`` what
        remains unverified; the returned ``handoff_rev`` feeds
        ``sw_resume_task`` after an interruption.
        """
        scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "create_handoff",
            CreateHandoffRequest(
                project_id=project_id,
                scope_id=scope_id,
                objective=objective,
                state=state or [],
                next_steps=next_steps or [],
                omissions=omissions or [],
            ),
        )
        return _payload(report)

    @mcp.tool
    async def sw_resume_task(
        project_id: str,
        scope_id: str = "",
        objective: str = "",
        handoff_rev: str = "",
        use_handoff: bool = True,
    ) -> dict:
        """Resume a task: continue handoff, verify catalog, rebuild context."""
        if use_handoff and handoff_rev:
            scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "resume_task",
            ResumeTaskRequest(
                project_id=project_id,
                scope_id=scope_id,
                objective=objective,
                handoff_rev=handoff_rev,
                use_handoff=use_handoff,
            ),
        )
        return {
            "project_id": report.project_id,
            "objective": report.objective,
            "progress": report.progress,
            "next_steps": report.next_steps,
            "handoff_resumed": report.handoff_resumed,
            "handoff_error": report.handoff_error,
            "mismatches": [m.model_dump(mode="json") for m in report.mismatches],
            "context_markdown": report.context.markdown,
        }

    @mcp.tool
    async def sw_record_decision(
        project_id: str,
        decision: str = "",
        rationale: str = "",
        replaces_entry_id: str = "",
        retire_entry_id: str = "",
        scope_id: str = "",
    ) -> dict:
        """Precipitate a design decision into PowerContext memory.

        ``replaces_entry_id`` revises an entry whose decision flipped,
        ``retire_entry_id`` retires one that no longer applies (history is
        kept); both take the ``entry_id`` this tool previously returned.
        """
        scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "record_decision",
            RecordDecisionRequest(
                project_id=project_id,
                scope_id=scope_id,
                decision=decision,
                rationale=rationale,
                replaces_entry_id=replaces_entry_id,
                retire_entry_id=retire_entry_id,
            ),
        )
        return _payload(report)

    @mcp.tool
    async def sw_report_progress(
        project_id: str,
        note: str,
        objective: str = "",
        state: list[str] | None = None,
        next_steps: list[str] | None = None,
        omissions: list[str] | None = None,
        update_handoff: bool = False,
        scope_id: str = "",
    ) -> dict:
        """Append a progress note to memory, optionally snapshot a handoff.

        With ``update_handoff`` the note also drives ``sw_handoff`` semantics
        (``state`` defaults to the note) and the reply carries ``handoff_rev``.
        """
        scope_id = await _scope(project_id, scope_id)
        report = await _invoke(
            "report_progress",
            ReportProgressRequest(
                project_id=project_id,
                scope_id=scope_id,
                note=note,
                update_handoff=update_handoff,
                objective=objective,
                state=list(state or []),
                next_steps=list(next_steps or []),
                omissions=list(omissions or []),
            ),
        )
        return _payload(report)

    @mcp.tool
    async def sw_verify(
        project_id: str,
        scope_id: str = "",
    ) -> dict:
        """Report workspace/catalog/activity/memory consistency checks.

        A scope that cannot be resolved degrades to "memory check skipped"
        instead of failing the report - the catalog cross-check is what
        matters most when PowerContext is unreachable.
        """
        scope_error = ""
        try:
            scope_id = await app.ensure_scope(project_id, scope_id)
        except SWError as exc:
            scope_id, scope_error = "", f"[{exc.code}] {exc.message}"
        report = await _invoke(
            "verify_state",
            VerifyStateRequest(
                project_id=project_id, scope_id=scope_id
            ),
        )
        if scope_error:
            report.notes.insert(0, f"scope unresolved: {scope_error}")
        return _payload(report)

    @mcp.tool
    async def sw_explain_source(
        project_id: str,
        artifact_id: str,
        depth: int = 1,
    ) -> dict:
        """Trace one artifact back to its evidence (clamped depth 1-3).

        Returns its source pointer, the upstream ``based_on`` chain with
        dangling refs surfaced, and the downstream relation neighbourhood.
        """
        report = await _invoke(
            "explain_source",
            ExplainSourceRequest(
                project_id=project_id,
                artifact_id=artifact_id,
                depth=depth,
            ),
        )
        return _payload(report)

    return mcp
