from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ....application.usecases.complete_task import CompleteTaskRequest
from ....application.usecases.create_handoff import CreateHandoffRequest
from ....application.usecases.get_context import GetContextRequest
from ....application.usecases.ingest_project import IngestProjectRequest
from ....application.usecases.resume_task import ResumeTaskRequest
from ....shared.errors import SWError

if TYPE_CHECKING:
    from ....shared.di import SpecWeaverApp


def _payload(result: Any) -> dict:
    return result.model_dump(mode="json")


def build_mcp(app: SpecWeaverApp) -> FastMCP:
    mcp = FastMCP("SpecWeaver")

    async def _invoke(name: str, request: Any) -> Any:
        usecase = app.usecases[name]
        try:
            return await usecase(request)
        except SWError as exc:
            raise ToolError(f"[{exc.code}] {exc.message}") from exc

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
            scope_id = await app.ensure_scope(project_id, scope_id)
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
            scope_id = await app.ensure_scope(project_id, scope_id)
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
        scope_id = await app.ensure_scope(project_id, scope_id)
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
            scope_id = await app.ensure_scope(project_id, scope_id)
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
            "mismatches": [m.model_dump(mode="json") for m in report.mismatches],
            "context_markdown": report.context.markdown,
        }

    return mcp
