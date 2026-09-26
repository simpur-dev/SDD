from __future__ import annotations

from datetime import datetime

from ....domain.entities import Artifact, ContextBundle, Task, TestRun
from ....domain.rules import byte_size
from ....domain.values import Budget
from .budget import FIXED_CHROME_BYTES, Budgeter
from .render import citations_for, format_test_run
from .sections import map_sections


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
    ) -> ContextBundle:
        """Assemble the bundle.

        ``relevance`` maps artifact id -> retrieval score; it orders entries
        inside each section so the budget drops the least relevant ones first
        (docs/01 §4.4 progressive disclosure).
        """
        sections = map_sections(valid, relevance)
        chrome = FIXED_CHROME_BYTES
        if last_test_run is not None:
            chrome += byte_size(format_test_run(last_test_run)) + 1
        # The Budgeter owns every byte decision, findings included: letting the
        # findings block reserve the whole budget is what used to zero out the
        # artifact sections under a tight CONTEXT__BUDGET_BYTES.
        decision = Budgeter(self._max_bytes).apply(sections, chrome, findings)

        # Audit A5: presentation objects must not smuggle 1536-float
        # embeddings into render_json / CLI --json / evidence payloads.
        def _presentable(
            artifacts: list[Artifact],
        ) -> list[Artifact]:
            return [
                artifact.model_copy(update={"embedding": None})
                for artifact in artifacts
            ]

        goal = _presentable(decision.sections.goal_and_constraints)
        design = _presentable(decision.sections.design_and_implementation)
        verification = _presentable(decision.sections.verification)

        used_bytes = chrome + decision.findings_bytes + decision.entry_bytes
        return ContextBundle(
            task=task,
            goal_and_constraints=goal,
            design_and_implementation=design,
            verification=verification,
            last_test_run=last_test_run,
            findings=decision.findings,
            citations=citations_for(goal + design + verification),
            budget=Budget(
                max_bytes=self._max_bytes,
                used_bytes=used_bytes,
                truncated=decision.truncated,
            ),
            generated_at=datetime.now(),
        )
