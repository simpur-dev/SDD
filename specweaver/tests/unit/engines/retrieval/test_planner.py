from __future__ import annotations

from fakes.inference import ScriptedLLM

from specweaver.application.engines.retrieval import (
    QueryPlanner,
    rule_keywords,
)
from specweaver.domain.enums import ArtifactType


def test_rule_keywords_keeps_terms_and_drops_stopwords() -> None:
    keywords = rule_keywords(
        "为铁路调度增加 发车时间 adjust the departure"
    )
    assert "adjust" in keywords
    assert "departure" in keywords
    assert any("发车时间" in token for token in keywords)
    assert "the" not in keywords


async def test_planner_falls_back_without_llm() -> None:
    plan = await QueryPlanner(None).plan("调整发车时间")
    assert plan.rationale == "rule-based planning"
    assert plan.keywords
    assert plan.objective == "调整发车时间"


async def test_planner_uses_llm_json() -> None:
    llm = ScriptedLLM(
        [
            '{"objective":"按站调整发车",'
            '"keywords":["发车","调整"],'
            '"modules":["schedule"],'
            '"types":["requirement"]}'
        ]
    )
    plan = await QueryPlanner(llm).plan("任意任务")
    assert plan.rationale == "llm planning"
    assert plan.keywords == ["发车", "调整"]
    assert plan.modules == ["schedule"]
    assert plan.types == [ArtifactType.requirement]
