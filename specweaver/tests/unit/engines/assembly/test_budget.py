from __future__ import annotations

from specweaver.application.engines.assembly import Budgeter, Sections
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType


def _requirement(artifact_id: str, cjk_chars: int) -> Artifact:
    return Artifact(
        id=artifact_id,
        project_id="p",
        type=ArtifactType.requirement,
        title=artifact_id,
        content="字" * cjk_chars,
    )


def test_budget_keeps_items_within_limit() -> None:
    sections = Sections(
        goal_and_constraints=[
            _requirement("REQ-1", 50),
            _requirement("REQ-2", 50),
        ],
        design_and_implementation=[],
        verification=[],
    )
    decision = Budgeter(4000).apply(sections, reserve_bytes=400)
    assert len(decision.sections.goal_and_constraints) == 2
    assert not decision.truncated


def test_budget_trims_and_prefers_goal_section() -> None:
    sections = Sections(
        goal_and_constraints=[_requirement("REQ-1", 50)],
        design_and_implementation=[_requirement("DES-1", 400)],
        verification=[],
    )
    decision = Budgeter(900).apply(sections, reserve_bytes=300)
    goal_ids = [a.id for a in decision.sections.goal_and_constraints]
    design_ids = [
        a.id for a in decision.sections.design_and_implementation
    ]
    assert goal_ids == ["REQ-1"]
    assert design_ids == []
    assert decision.truncated
