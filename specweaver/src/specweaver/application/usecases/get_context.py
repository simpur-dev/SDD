from __future__ import annotations

import uuid

from pydantic import BaseModel

from ...domain.entities import ContextBundle, Task
from ..engines.assembly import AssemblyEngine, render_markdown
from ..engines.retrieval import RetrievalEngine
from ..engines.validity import ValidityEngine
from ..engines.validity.pipeline import ExcludedArtifact
from .base import UseCase


class GetContextRequest(BaseModel):
    project_id: str
    task_text: str
    base_ref: str | None = None


class ContextResult(BaseModel):
    bundle: ContextBundle
    markdown: str
    excluded: list[ExcludedArtifact] = []


class GetContext(UseCase):
    """Core read path: retrieval -> validity -> assembly."""

    name = "get_context"

    def __init__(
        self,
        retrieval: RetrievalEngine,
        validity: ValidityEngine,
        assembly: AssemblyEngine,
        telemetry,
        workspace=None,
    ) -> None:
        super().__init__(telemetry)
        self._retrieval = retrieval
        self._validity = validity
        self._assembly = assembly
        self._workspace = workspace

    async def __call__(
        self, request: GetContextRequest
    ) -> ContextResult:
        with self.span():
            retrieved = await self._retrieval.run(
                request.project_id, request.task_text
            )
            validity_result = await self._validity.run(
                retrieved.scored,
                current_ref=request.base_ref,
                workspace=self._workspace,
            )
            task = Task(
                id=f"task-{uuid.uuid4().hex[:10]}",
                project_id=request.project_id,
                title=request.task_text[:80],
                objective=request.task_text,
                base_ref=request.base_ref,
            )
            bundle = await self._assembly.run(
                task,
                validity_result.valid,
                validity_result.findings,
            )
            return ContextResult(
                bundle=bundle,
                markdown=render_markdown(bundle),
                excluded=validity_result.excluded,
            )
