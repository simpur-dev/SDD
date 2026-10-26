from __future__ import annotations

from specweaver.domain.ports.handoff import (
    HandoffDraft,
    HandoffView,
)
from specweaver.shared.errors import SWError


class InMemoryHandoff:
    def __init__(self) -> None:
        self._stored: dict[str, HandoffView] = {}
        self._counter = 0

    async def prepare_current(
        self, draft: HandoffDraft
    ) -> HandoffView:
        # Mirrors the PowerContext prepare-current contract (docs/02 §7.4):
        # non-blank objective and at least one non-blank state claim.
        if not draft.objective.strip():
            raise SWError("handoff requires a non-empty objective")
        if not any(s.strip() for s in draft.state):
            raise SWError("handoff requires at least one state claim")
        first_next = next(
            (n.strip() for n in draft.next_steps if n.strip()), ""
        )
        return HandoffView(
            scope_id=draft.scope_id,
            objective=draft.objective,
            progress="\n".join(s for s in draft.state if s.strip()),
            next_steps=[first_next] if first_next else [],
            unverified=[o for o in draft.omissions if o.strip()],
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
