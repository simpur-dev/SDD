from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.catalog import CatalogPort
from ...domain.ports.handoff import HandoffPort
from ...domain.ports.workspace import WorkspacePort
from ...shared.errors import SWError
from ..engines.validity.lifecycle import LifecycleValidator
from .base import UseCase
from .consistency import StateMismatch, workspace_mismatches
from .get_context import ContextResult, GetContext, GetContextRequest


class ResumeTaskRequest(BaseModel):
    project_id: str
    scope_id: str = ""
    objective: str = ""
    handoff_rev: str = ""
    use_handoff: bool = True


class ResumeReport(BaseModel):
    project_id: str
    objective: str
    progress: str = ""
    next_steps: list[str] = []
    handoff_resumed: bool
    handoff_error: str = ""
    mismatches: list[StateMismatch]
    context: ContextResult


class ResumeTask(UseCase):
    """Continue a task: resume handoff, verify catalog against the workspace."""

    name = "resume_task"

    def __init__(
        self,
        catalog: CatalogPort | None,
        handoff: HandoffPort | None,
        workspace: WorkspacePort,
        get_context: GetContext,
        telemetry,
        lifecycle: LifecycleValidator | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._catalog = catalog
        self._handoff = handoff
        self._workspace = workspace
        self._get_context = get_context
        self._lifecycle = lifecycle or LifecycleValidator()

    async def __call__(self, request: ResumeTaskRequest) -> ResumeReport:
        with self.span():
            view = None
            handoff_error = ""
            if (
                request.use_handoff
                and request.scope_id
                and request.handoff_rev
                and self._handoff is not None
            ):
                try:
                    view = await self._handoff.continue_(
                        request.scope_id, request.handoff_rev
                    )
                except SWError as exc:
                    # audit B4: degrade to "no handoff" but surface why;
                    # unexpected exception types must crash loudly instead
                    view = None
                    handoff_error = exc.message[:200]

            objective = request.objective
            progress = ""
            next_steps: list[str] = []
            if view is not None:
                objective = objective or view.objective
                progress = view.progress
                next_steps = list(view.next_steps)

            mismatches: list[StateMismatch] = []
            if self._catalog is not None:
                mismatches = await workspace_mismatches(
                    self._catalog,
                    self._workspace,
                    request.project_id,
                    self._lifecycle,
                )

            objective = objective or "resume current work"
            current_ref = await self._workspace.current_ref()
            context = await self._get_context(
                GetContextRequest(
                    project_id=request.project_id,
                    task_text=objective,
                    base_ref=current_ref,
                )
            )

            return ResumeReport(
                project_id=request.project_id,
                objective=objective,
                progress=progress,
                next_steps=next_steps,
                handoff_resumed=view is not None,
                handoff_error=handoff_error,
                mismatches=mismatches,
                context=context,
            )
