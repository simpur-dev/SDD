from __future__ import annotations

from datetime import datetime

from ....domain.entities import Artifact, ContextBundle, Task, TestRun
from ....domain.rules import byte_size
from ....domain.values import Budget, MemoryNote
from .budget import FIXED_CHROME_BYTES, BudgetDecision, Budgeter, entry_cost
from .render import (
    citations_for,
    format_test_run,
    memory_block,
    render_markdown,
)
from .sections import map_sections


def _presentable(artifacts: list[Artifact]) -> list[Artifact]:
    """Audit A5: drop the 1536-float embedding so it cannot leak into
    render_json, CLI --json or the evidence payloads."""
    return [
        artifact.model_copy(update={"embedding": None})
        for artifact in artifacts
    ]


class AssemblyEngine:
    """Maps valid artifacts to sections, trims to budget and builds the bundle."""

    def __init__(self, max_bytes: int = 8000) -> None:
        self._max_bytes = max_bytes

    async def run(
        self,
        task: Task,
        valid: list[Artifact],
        findings,
        last_test_run: TestRun | None = None,
        relevance: dict[str, float] | None = None,
        memory_notes: list[MemoryNote] | None = None,
    ) -> ContextBundle:
        """Assemble the bundle.

        ``relevance`` maps artifact id -> retrieval score; it orders entries
        inside each section so the budget drops the least relevant ones first
        (docs/01 §4.4 progressive disclosure).
        """
        sections = map_sections(valid, relevance)
        notes = memory_notes or []
        chrome = FIXED_CHROME_BYTES + byte_size(memory_block(notes))
        if last_test_run is not None:
            chrome += byte_size(format_test_run(last_test_run)) + 1
        # The Budgeter owns every byte decision, findings included: letting the
        # findings block reserve the whole budget is what used to zero out the
        # artifact sections under a tight CONTEXT__BUDGET_BYTES.
        budgeter = Budgeter(self._max_bytes)
        decision = budgeter.apply(sections, chrome, findings)

        def _bundle(decision: BudgetDecision) -> ContextBundle:
            goal = _presentable(decision.sections.goal_and_constraints)
            design = _presentable(decision.sections.design_and_implementation)
            verification = _presentable(decision.sections.verification)
            return ContextBundle(
                task=task,
                goal_and_constraints=goal,
                design_and_implementation=design,
                verification=verification,
                last_test_run=last_test_run,
                findings=decision.findings,
                memory_notes=notes,
                citations=citations_for(goal + design + verification),
                budget=Budget(
                    max_bytes=self._max_bytes,
                    used_bytes=(
                        chrome
                        + decision.findings_bytes
                        + decision.entry_bytes
                    ),
                    truncated=decision.truncated,
                ),
                generated_at=datetime.now(),
            )

        bundle = _bundle(decision)
        # The budget is a promise about the emitted text, not about the
        # accounting model, and the model can be optimistic in ways only the
        # render shows: a UTF-8 heavy task title costs 3 bytes per character,
        # and emitting the "truncated" warning spends a line no artifact paid
        # for. Measure the real render and pay the overshoot out of the entry
        # allowance, repeatedly - one pass is not enough, because the pass that
        # drops an entry is also the pass that adds the warning it must pay for.
        all_entries = [
            *sections.goal_and_constraints,
            *sections.design_and_implementation,
            *sections.verification,
        ]
        reserve = chrome
        for _ in range(len(all_entries) + 1):
            overshoot = byte_size(render_markdown(bundle)) - self._max_bytes
            kept = [
                *decision.sections.goal_and_constraints,
                *decision.sections.design_and_implementation,
                *decision.sections.verification,
            ]
            if overshoot <= 0 or not kept:
                break
            # an overshoot below the cheapest entry would change nothing, so a
            # pass always retires at least one entry and the loop terminates
            reserve += max(overshoot, min(entry_cost(a) for a in kept))
            decision = budgeter.apply(sections, reserve, findings)
            bundle = _bundle(decision)
        return bundle
