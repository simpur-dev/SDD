from __future__ import annotations

from dataclasses import dataclass

from ....domain.rules import byte_size
from .render import entry_block
from .sections import Sections

# Headings, status block and budget block that are always present.
FIXED_CHROME_BYTES = 600
_ENTRY_GAP_BYTES = 2


@dataclass
class BudgetDecision:
    sections: Sections
    entry_bytes: int
    truncated: bool


class Budgeter:
    """Trims sections to a UTF-8 byte budget; findings/chrome are reserved first."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    def apply(
        self, sections: Sections, reserve_bytes: int
    ) -> BudgetDecision:
        available = self._max_bytes - reserve_bytes
        used = 0
        truncated = False

        def fit(items: list) -> list:
            nonlocal used, truncated
            kept: list = []
            for artifact in items:
                size = byte_size(entry_block(artifact)) + _ENTRY_GAP_BYTES
                if used + size > available:
                    truncated = True
                    continue
                used += size
                kept.append(artifact)
            return kept

        kept_sections = Sections(
            goal_and_constraints=fit(sections.goal_and_constraints),
            design_and_implementation=fit(
                sections.design_and_implementation
            ),
            verification=fit(sections.verification),
        )
        return BudgetDecision(
            sections=kept_sections,
            entry_bytes=used,
            truncated=truncated,
        )
