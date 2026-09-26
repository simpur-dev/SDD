"""ReportProgress: append a progress note to memory, optionally snapshot a
handoff through the CreateHandoff usecase (composition, no duplication)."""
from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.memory import MemoryEntry, MemoryPort
from ...shared.errors import SWError
from .base import UseCase
from .create_handoff import CreateHandoff, CreateHandoffRequest


class ReportProgressRequest(BaseModel):
    project_id: str
    scope_id: str = ""
    note: str = ""
    update_handoff: bool = False
    objective: str = ""
    state: list[str] = []
    next_steps: list[str] = []
    omissions: list[str] = []


class ReportProgressReport(BaseModel):
    entry_id: str
    handoff_rev: str | None = None


class ReportProgress(UseCase):
    """Precipitate "what just happened" and optionally commit a handoff."""

    name = "report_progress"

    def __init__(
        self,
        telemetry,
        memory: MemoryPort | None = None,
        create_handoff: CreateHandoff | None = None,
    ) -> None:
        super().__init__(telemetry)
        self._memory = memory
        self._create_handoff = create_handoff

    async def __call__(
        self, request: ReportProgressRequest
    ) -> ReportProgressReport:
        with self.span():
            if self._memory is None:
                raise SWError(
                    "report_progress requires PowerContext memory; "
                    "run `specweaver doctor`"
                )
            if not request.scope_id:
                raise SWError(
                    "report_progress requires scope_id; the driving layer "
                    "resolves it via app.ensure_scope"
                )
            if not request.note.strip():
                raise SWError(
                    "report_progress requires a non-empty note"
                )
            entry = await self._memory.remember(
                MemoryEntry(
                    scope_id=request.scope_id,
                    kind="progress",
                    content=request.note.strip(),
                    tags=["progress", request.project_id],
                )
            )
            handoff_rev = None
            if request.update_handoff:
                if self._create_handoff is None:
                    raise SWError(
                        "update_handoff requires the CreateHandoff usecase"
                    )
                handoff = await self._create_handoff(
                    CreateHandoffRequest(
                        project_id=request.project_id,
                        scope_id=request.scope_id,
                        objective=request.objective or request.note.strip(),
                        state=request.state or [request.note.strip()],
                        next_steps=request.next_steps,
                        omissions=request.omissions,
                    )
                )
                handoff_rev = handoff.handoff_rev
            return ReportProgressReport(
                entry_id=entry.id or "", handoff_rev=handoff_rev
            )
