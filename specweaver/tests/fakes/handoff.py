from __future__ import annotations

from specweaver.domain.ports.handoff import (
    HandoffDraft,
    HandoffView,
)


class InMemoryHandoff:
    def __init__(self) -> None:
        self._stored: dict[str, HandoffView] = {}
        self._counter = 0

    async def prepare_current(
        self, draft: HandoffDraft
    ) -> HandoffView:
        return HandoffView(
            scope_id=draft.scope_id,
            objective=draft.objective,
            progress="\n".join(draft.state),
            next_steps=draft.next_steps,
            unverified=draft.omissions,
            raw={"draft": draft.model_dump()},
        )

    async def commit(self, view: HandoffView) -> HandoffView:
        self._counter += 1
        view.rev = f"handoff:handoff:{self._counter}"
        self._stored[view.rev] = view
        return view

    async def continue_(
        self, scope_id: str, rev: str
    ) -> HandoffView:
        return self._stored.get(
            rev, HandoffView(scope_id=scope_id, rev=rev)
        )

    async def record_outcome(
        self, scope_id: str, source_id: str, outcome: dict
    ) -> None:
        return None
