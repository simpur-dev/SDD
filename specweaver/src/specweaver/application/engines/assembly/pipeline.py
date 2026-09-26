from __future__ import annotations

from datetime import datetime

from ....domain.entities import Artifact, ContextBundle, Task, TestRun
from ....domain.rules import byte_size
from ....domain.values import Budget
from .budget import FIXED_CHROME_BYTES, Budgeter
from .render import citations_for, findings_block, format_test_run
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
    ) -> ContextBundle:
        sections = map_sections(valid)
        reserve = FIXED_CHROME_BYTES + byte_size(
            findings_block(findings)
        )
        if last_test_run is not None:
            reserve += byte_size(format_test_run(last_test_run)) + 1
        decision = Budgeter(self._max_bytes).apply(sections, reserve)

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

        used_bytes = reserve + decision.entry_bytes
        return ContextBundle(
            task=task,
            goal_and_constraints=goal,
            design_and_implementation=design,
            verification=verification,
            last_test_run=last_test_run,
            findings=findings,
            citations=citations_for(goal + design + verification),
            budget=Budget(
                max_bytes=self._max_bytes,
                used_bytes=used_bytes,
                truncated=decision.truncated,
            ),
            generated_at=datetime.now(),
        )
