"""RecordDecision: precipitate design decisions into PowerContext memory.

Three actions on one entry lifecycle: remember a new decision, revise a
superseded one (the decision flipped), or retire one (no longer applies)
- consuming MemoryPort.revise/retire/list_entries.
"""
from __future__ import annotations

from pydantic import BaseModel

from ...domain.ports.memory import MemoryEntry, MemoryPort
from ...shared.errors import SWError
from .base import UseCase


class RecordDecisionRequest(BaseModel):
    project_id: str
    scope_id: str = ""
    decision: str = ""
    rationale: str = ""
    replaces_entry_id: str = ""
    retire_entry_id: str = ""


class RecordDecisionReport(BaseModel):
    action: str  # remembered | revised | retired
    entry_id: str
    revision: str = ""


class RecordDecision(UseCase):
    """Write a decision into memory, revising or retiring an earlier one."""

    name = "record_decision"

    def __init__(
        self, telemetry, memory: MemoryPort | None = None
    ) -> None:
        super().__init__(telemetry)
        self._memory = memory

    async def __call__(
        self, request: RecordDecisionRequest
    ) -> RecordDecisionReport:
        with self.span():
            if self._memory is None:
                raise SWError(
                    "record_decision requires PowerContext memory; "
                    "run `specweaver doctor`"
                )
            if not request.scope_id:
                raise SWError(
                    "record_decision requires scope_id; the driving layer "
                    "resolves it via app.ensure_scope"
                )
            if request.replaces_entry_id and request.retire_entry_id:
                raise SWError(
                    "record_decision takes either replaces_entry_id or "
                    "retire_entry_id, not both"
                )
            if request.retire_entry_id:
                entry = await self._find(
                    request.scope_id, request.retire_entry_id
                )
                await self._memory.retire(
                    self._citation(entry),
                    reason=(
                        request.decision.strip()
                        or "retired by SpecWeaver"
                    ),
                )
                return RecordDecisionReport(
                    action="retired", entry_id=request.retire_entry_id
                )
            content = self._content(request)
            if request.replaces_entry_id:
                entry = await self._find(
                    request.scope_id, request.replaces_entry_id
                )
                revised = await self._memory.revise(
                    self._citation(entry),
                    content,
                    reason="superseded by a new decision",
                )
                out = revised
            else:
                out = await self._memory.remember(
                    MemoryEntry(
                        scope_id=request.scope_id,
                        kind="decision",
                        content=content,
                        tags=["decision", request.project_id],
                    )
                )
            return RecordDecisionReport(
                action=(
                    "revised"
                    if request.replaces_entry_id
                    else "remembered"
                ),
                entry_id=out.id or "",
                revision=(
                    str(out.citation.source.checksum or "")
                    if out.citation
                    else ""
                ),
            )

    async def _find(self, scope_id: str, entry_id: str) -> MemoryEntry:
        for entry in await self._memory.list_entries(
            scope_id, include_inactive=True
        ):
            if entry.id == entry_id:
                return entry
        raise SWError(
            f"memory entry not found in scope {scope_id}: {entry_id}"
        )

    @staticmethod
    def _citation(entry: MemoryEntry):
        if entry.citation is None:
            raise SWError(f"memory entry {entry.id} carries no citation")
        return entry.citation

    @staticmethod
    def _content(request: RecordDecisionRequest) -> str:
        if not request.decision.strip():
            raise SWError(
                "record_decision requires a non-empty decision "
                "(unless retiring)"
            )
        text = request.decision.strip()
        if request.rationale.strip():
            text += f"\nRationale: {request.rationale.strip()}"
        return text
