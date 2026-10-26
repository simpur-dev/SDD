from __future__ import annotations

from specweaver.application.engines.assembly import Budgeter, Sections
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType, FindingKind
from specweaver.domain.values import Finding


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


def test_budget_zero_drops_all_without_error() -> None:
    sections = Sections(
        goal_and_constraints=[_requirement("REQ-1", 10)],
        design_and_implementation=[],
        verification=[],
    )
    decision = Budgeter(0).apply(sections, reserve_bytes=0)
    assert decision.sections.goal_and_constraints == []
    assert decision.truncated


def test_budget_negative_available_drops_all() -> None:
    sections = Sections(
        goal_and_constraints=[_requirement("REQ-1", 10)],
        design_and_implementation=[],
        verification=[],
    )
    decision = Budgeter(100).apply(sections, reserve_bytes=900)
    assert decision.sections.goal_and_constraints == []
    assert decision.truncated
    assert decision.entry_bytes == 0


def _findings(count: int, chars: int = 120) -> list[Finding]:
    return [
        Finding(kind=FindingKind.gap, message="缺" * chars)
        for _ in range(count)
    ]


def test_findings_can_no_longer_starve_the_constraint_floor() -> None:
    """Regression measured on the tight-budget gold-set run.

    With a 1500-byte budget the rendered findings block used to be reserved
    upfront, which left nothing for the artifact sections and dropped every
    gold requirement/rule - silently undoing the retrieval constraint floor.
    """
    sections = Sections(
        goal_and_constraints=[
            _requirement("RULE-1", 30),
            _requirement("REQ-1", 30),
        ],
        design_and_implementation=[_requirement("CODE-1", 900)],
        verification=[],
    )
    findings = _findings(8)

    decision = Budgeter(1500).apply(sections, 600, findings)

    assert [
        a.id for a in decision.sections.goal_and_constraints
    ] == ["RULE-1", "REQ-1"]
    assert decision.sections.design_and_implementation == []
    assert len(decision.findings) < len(findings)
    assert decision.truncated
    assert 600 + decision.findings_bytes + decision.entry_bytes <= 1500


def test_no_findings_leaves_the_reserve_math_unchanged() -> None:
    sections = Sections([_requirement("REQ-1", 50)], [], [])
    decision = Budgeter(4000).apply(sections, 400)

    assert decision.entry_bytes > 0
    assert decision.findings == []
    assert not decision.truncated
