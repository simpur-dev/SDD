from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ....domain.rules import byte_size
from ....domain.values import Finding
from .render import entry_block, findings_block
from .sections import Sections

# Headings, status block and budget block that are always present.
FIXED_CHROME_BYTES = 600
_ENTRY_GAP_BYTES = 2

# Findings carry the conflict/gap signal, artifacts the evidence: neither may
# starve the other. The goal section (rules + requirements) is the constraint
# floor retrieval worked to guarantee, so it is reserved before findings get
# anything - otherwise a chatty findings block empties the evidence sections.
GOAL_FLOOR_SHARE = 0.4
FINDINGS_SHARE = 0.35


def entry_cost(artifact) -> int:
    """Conservative UTF-8 cost of emitting one artifact.

    Beyond its own block, an entry also appends its id to the ④ "sources
    cited" line, so that is charged here; measuring the full render afterwards
    is what catches whatever this still under-counts.
    """
    return (
        byte_size(entry_block(artifact))
        + _ENTRY_GAP_BYTES
        + byte_size(artifact.id)
    )


@dataclass
class BudgetDecision:
    sections: Sections
    findings: list[Finding] = field(default_factory=list)
    findings_bytes: int = 0
    entry_bytes: int = 0
    truncated: bool = False


class Budgeter:
    """Trims findings and sections to a UTF-8 byte budget.

    Sections fill in priority order - rules and requirements first, then
    design/code, then tests - so a squeezed budget loses implementation detail
    before it loses the constraint floor that retrieval deliberately guarantees.
    """

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes

    def _fit_findings(
        self, findings: Sequence[Finding]
    ) -> tuple[list[Finding], int]:
        floor = int(self._max_bytes * GOAL_FLOOR_SHARE)
        allowance = min(
            int(self._max_bytes * FINDINGS_SHARE),
            max(self._max_bytes - FIXED_CHROME_BYTES - floor, 0),
        )
        for count in range(len(findings), -1, -1):
            size = byte_size(findings_block(list(findings[:count])))
            if size <= allowance:
                return list(findings[:count]), size
        return [], 0

    def apply(
        self,
        sections: Sections,
        reserve_bytes: int,
        findings: Sequence[Finding] = (),
    ) -> BudgetDecision:
        kept_findings, findings_bytes = self._fit_findings(findings)
        available = max(
            self._max_bytes - reserve_bytes - findings_bytes, 0
        )
        used = 0
        truncated = len(kept_findings) < len(findings)
        groups: list[list] = []
        exhausted = False

        for items in (
            sections.goal_and_constraints,
            sections.design_and_implementation,
            sections.verification,
        ):
            kept: list = []
            if exhausted:
                groups.append(kept)
                continue
            for artifact in items:
                cost = entry_cost(artifact)
                if used + cost > available:
                    # Strict priority, both directions. Trying a smaller entry
                    # from the same section, or letting a later section pick up
                    # the remainder, spends the budget on less important
                    # evidence than the entry we just had to drop - which is how
                    # a 1500-byte bundle ended up carrying an unrelated publish
                    # rule and a publish code block while dropping the
                    # requirement and design the task was about (docs/01 §11).
                    truncated = True
                    exhausted = True
                    break
                used += cost
                kept.append(artifact)
            groups.append(kept)

        return BudgetDecision(
            sections=Sections(*groups),
            findings=kept_findings,
            findings_bytes=findings_bytes,
            entry_bytes=used,
            truncated=truncated,
        )
