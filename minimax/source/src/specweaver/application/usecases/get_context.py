from __future__ import annotations

import time
import uuid

from pydantic import BaseModel

from ...domain.entities import ContextBundle, Task
from ...domain.ports.activity import ActivityLogPort
from ...domain.ports.memory import MemoryPort
from ...domain.values import MemoryNote
from ...shared.errors import SWError
from ..engines.assembly import AssemblyEngine, render_markdown
from ..engines.retrieval import RetrievalEngine
from ..engines.validity import ValidityEngine
from ..engines.validity.pipeline import ExcludedArtifact
from .base import UseCase


class GetContextRequest(BaseModel):
    project_id: str
    task_text: str
    base_ref: str | None = None
    # set by the driving layer only; the usecase never resolves scopes
    scope_id: str = ""


class ContextResult(BaseModel):
    bundle: ContextBundle
    markdown: str
    excluded: list[ExcludedArtifact] = []
    memory_error: str = ""


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
        activity: ActivityLogPort | None = None,
        memory: MemoryPort | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._retrieval = retrieval
        self._validity = validity
        self._assembly = assembly
        self._workspace = workspace
        self._activity = activity
        self._memory = memory

    async def __call__(
        self, request: GetContextRequest
    ) -> ContextResult:
        with self.span():
            retrieved = await self._retrieval.run(
                request.project_id, request.task_text
            )
            self.telemetry.record_metric("recall", len(retrieved.scored))
            validity_result = await self._validity.run(
                retrieved.scored,
                current_ref=request.base_ref,
                workspace=self._workspace,
            )
            self.telemetry.record_metric(
                "valid", len(validity_result.valid)
            )
            self.telemetry.record_metric(
                "excluded", len(validity_result.excluded)
            )
            last_test_run = None
            if self._activity is not None:
                runs = await self._activity.list_test_runs(
                    request.project_id
                )
                last_test_run = runs[0] if runs else None
            notes: list[MemoryNote] = []
            memory_error = ""
            if self._memory is not None and request.scope_id:
                # PowerContext is read back, not only written to: the
                # decisions and progress precipitated earlier belong in the
                # task-status section of the bundle.
                try:
                    entries = await self._memory.search(
                        request.scope_id, request.task_text, n=6
                    )
                except SWError as exc:
                    memory_error = exc.message[:200]
                else:
                    notes = [
                        MemoryNote(
                            kind=entry.kind,
                            # one display line per note: memory text can be a
                            # whole pasted document, and the bundle must stay
                            # well-formed markdown
                            content=" ".join(entry.content.split())[:200],
                            citation=entry.citation,
                        )
                        for entry in entries
                        if entry.content.strip()
                    ]
            task = Task(
                id=f"task-{uuid.uuid4().hex[:10]}",
                project_id=request.project_id,
                title=request.task_text[:80],
                objective=request.task_text,
                base_ref=request.base_ref,
            )
            started = time.perf_counter()
            bundle = await self._assembly.run(
                task,
                validity_result.valid,
                validity_result.findings,
                last_test_run=last_test_run,
                relevance={
                    scored.artifact.id: scored.score
                    for scored in retrieved.scored
                },
                memory_notes=notes,
            )
            self.telemetry.record_metric(
                "assembly_ms",
                round((time.perf_counter() - started) * 1000, 1),
            )
            self.telemetry.record_metric(
                "findings", len(bundle.findings)
            )
            if bundle.budget is not None:
                self.telemetry.record_metric(
                    "bundle_bytes", bundle.budget.used_bytes
                )
            self.telemetry.record_metric("memory_notes", len(notes))
            return ContextResult(
                bundle=bundle,
                markdown=render_markdown(bundle),
                excluded=validity_result.excluded,
                memory_error=memory_error,
            )
