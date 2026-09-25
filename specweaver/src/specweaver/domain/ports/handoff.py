from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class HandoffDraft(BaseModel):
    """Input for packaging the current task state into a handoff."""

    scope_id: str
    source_id: str = ""
    objective: str = ""
    state: list[str] = []
    next_steps: list[str] = []
    omissions: list[str] = []
    disposition: str = "continuable"


class HandoffView(BaseModel):
    rev: str = ""
    scope_id: str
    objective: str = ""
    progress: str = ""
    next_steps: list[str] = []
    unverified: list[str] = []
    raw: dict = {}


class HandoffPort(Protocol):
    async def prepare_current(self, draft: HandoffDraft) -> HandoffView: ...

    async def commit(self, view: HandoffView) -> HandoffView: ...

    async def continue_(self, scope_id: str, rev: str) -> HandoffView: ...

    async def acknowledge(self, view: HandoffView) -> None: ...

    async def record_outcome(
        self, scope_id: str, source_id: str, outcome: dict
    ) -> None: ...
