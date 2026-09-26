from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.catalog import ArtifactFilter, CatalogPort
from ...domain.ports.handoff import HandoffPort
from ...domain.ports.workspace import WorkspacePort
from ..engines.validity.lifecycle import LifecycleValidator
from .base import UseCase
from .get_context import ContextResult, GetContext, GetContextRequest


class StateMismatch(BaseModel):
    artifact_id: str
    source_uri: str
    issue: str


class ResumeTaskRequest(BaseModel):
    project_id: str
    scope_id: str
    objective: str = ""
    handoff_rev: str = ""
    use_handoff: bool = True


class ResumeReport(BaseModel):
    project_id: str
    objective: str
    progress: str = ""
    next_steps: list[str] = []
    handoff_resumed: bool
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
            if (
                request.use_handoff
                and request.handoff_rev
                and self._handoff is not None
            ):
                try:
                    view = await self._handoff.continue_(
                        request.scope_id, request.handoff_rev
                    )
                except Exception:  # noqa: BLE001
                    view = None

            objective = request.objective
            progress = ""
            next_steps: list[str] = []
            if view is not None:
                objective = objective or view.objective
                progress = view.progress
                next_steps = list(view.next_steps)

            mismatches: list[StateMismatch] = []
            if self._catalog is not None:
                artifacts = await self._catalog.list_artifacts(
                    ArtifactFilter(project_id=request.project_id)
                )
                for artifact in artifacts:
                    issue = await self._lifecycle.verify_engineering(
                        artifact, self._workspace
                    )
                    if issue is not None:
                        uri = (
                            artifact.source.uri
                            if artifact.source is not None
                            else ""
                        )
                        mismatches.append(
                            StateMismatch(
                                artifact_id=artifact.id,
                                source_uri=uri,
                                issue=issue,
                            )
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
                mismatches=mismatches,
                context=context,
            )
