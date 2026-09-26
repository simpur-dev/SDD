"""Constraint-floor candidates must not win scarce slots by id order.

The retrieval engine injects every active requirement/rule with no score so a
task can never lose the constraints it did not mention (docs/01 §7.1). Section
ordering keys on relevance, so those items used to fall through to
``(module, id)`` - and a 2-3 entry budget then delivered whichever id sorted
first instead of whichever constraint the task is about, which is what the gold
set measured as "we deliver more and hit less" (docs/01 §11).
"""
from __future__ import annotations

from specweaver.application.engines.assembly.sections import map_sections
from specweaver.domain.entities import Artifact
from specweaver.domain.enums import ArtifactType


def _rule(rule_id: str, module: str, content: str) -> Artifact:
    return Artifact(
        id=rule_id,
        project_id="p",
        type=ArtifactType.rule,
        module=module,
        title=rule_id,
        content=content,
    )


def test_unscored_constraints_order_by_task_overlap_not_by_id() -> None:
    irrelevant = _rule("RULE-A", "publish", "发布前须通过全部回归测试")
    relevant = _rule("RULE-B", "interval", "相邻站发车间隔不得低于 5 分钟")

    ordered = map_sections(
        [irrelevant, relevant],
        relevance={},
        task_text="调整 发车时间 相邻站 间隔",
    )

    assert [a.id for a in ordered.goal_and_constraints] == [
        "RULE-B",
        "RULE-A",
    ]


def test_scored_candidates_keep_the_relevance_order() -> None:
    first = _rule("RULE-A", "m", "相邻站 间隔")
    second = _rule("RULE-B", "m", "相邻站 间隔")

    ordered = map_sections(
        [first, second],
        relevance={first.id: 0.1, second.id: 0.2},
        task_text="相邻站 间隔",
    )

    assert [a.id for a in ordered.goal_and_constraints] == [
        "RULE-B",
        "RULE-A",
    ]


def test_no_task_text_leaves_the_old_order_intact() -> None:
    a = _rule("RULE-A", "m", "x")
    b = _rule("RULE-B", "m", "x")

    ordered = map_sections([b, a], relevance={}, task_text="")

    assert [x.id for x in ordered.goal_and_constraints] == [
        "RULE-A",
        "RULE-B",
    ]
