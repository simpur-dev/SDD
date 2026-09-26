from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.handoff import HandoffDraft, HandoffPort
from ...shared.errors import SWError
from .base import UseCase


class CreateHandoffRequest(BaseModel):
    project_id: str
    scope_id: str = ""
    objective: str = ""
    state: list[str] = []
    next_steps: list[str] = []
    omissions: list[str] = []
    source_id: str = ""


class CreateHandoffReport(BaseModel):
    project_id: str
    scope_id: str
    handoff_rev: str
    objective: str
    next_steps: list[str] = []
    unverified: list[str] = []


class CreateHandoff(UseCase):
    """Package the current task state into a committed PowerContext handoff."""

    name = "create_handoff"

    def __init__(self, handoff: HandoffPort, telemetry) -> None:
        super().__init__(telemetry)
        self._handoff = handoff

    async def __call__(
        self, request: CreateHandoffRequest
    ) -> CreateHandoffReport:
        with self.span():
            if not request.scope_id:
                raise SWError(
                    "create_handoff requires scope_id; the driving layer "
                    "resolves it via app.ensure_scope"
                )
            if not request.objective.strip():
                raise SWError("create_handoff requires a non-empty objective")
            if not any(s.strip() for s in request.state):
                raise SWError(
                    "create_handoff requires at least one non-blank state "
                    "claim"
                )
            draft = HandoffDraft(
                scope_id=request.scope_id,
                source_id=request.source_id,
                objective=request.objective,
                state=list(request.state),
                next_steps=list(request.next_steps),
                omissions=list(request.omissions),
            )
            view = await self._handoff.prepare_current(draft)
            view = await self._handoff.commit(view)
            return CreateHandoffReport(
                project_id=request.project_id,
                scope_id=view.scope_id,
                handoff_rev=view.rev,
                objective=view.objective,
                next_steps=list(view.next_steps),
                unverified=list(view.unverified),
            )
