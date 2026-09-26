from __future__ import annotations

from fakes.inference import RaisingLLM, ScriptedLLM

from specweaver.application.engines.retrieval import (
    QueryPlanner,
    rule_keywords,
)
from specweaver.domain.enums import ArtifactType
from specweaver.domain.ports.inference import CompletionResult
from specweaver.domain.values import TokenUsage
from specweaver.shared.telemetry import Telemetry


class _UsageLLM:
    """LLM stub that reports token usage on every completion."""

    def __init__(self, reply: str, usage: TokenUsage) -> None:
        self._reply = reply
        self._usage = usage

    async def complete(
        self, prompt: str, schema: dict | None = None
    ) -> CompletionResult:
        return CompletionResult(
            text=self._reply,
            structured={"objective": "o"} if schema else None,
            usage=self._usage,
        )


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


async def test_planner_falls_back_when_llm_raises() -> None:
    plan = await QueryPlanner(RaisingLLM()).plan("调整发车时间")
    assert plan.rationale == "rule-based planning"
    assert plan.keywords  # rule keywords are still produced


async def test_planner_falls_back_on_invalid_json() -> None:
    llm = ScriptedLLM(["not a json object"])
    plan = await QueryPlanner(llm).plan("调整发车时间")
    assert plan.rationale == "rule-based planning"


async def test_planner_reports_llm_usage_to_telemetry() -> None:
    tel = Telemetry()
    planner = QueryPlanner(
        _UsageLLM("{}", TokenUsage(prompt_tokens=120, completion_tokens=18)),
        tel,
    )
    with tel.span("get_context") as rec:
        await planner.plan("任意任务")
    assert rec.llm_calls == 1
    assert rec.prompt_tokens == 120
    assert rec.completion_tokens == 18


async def test_planner_counts_failed_llm_fallback_nothing() -> None:
    tel = Telemetry()
    planner = QueryPlanner(RaisingLLM(), tel)
    with tel.span("get_context") as rec:
        plan = await planner.plan("调整发车时间")
    assert plan.rationale == "rule-based planning"
    assert rec.llm_calls == 0


async def test_planner_without_span_does_not_crash() -> None:
    tel = Telemetry()
    planner = QueryPlanner(
        _UsageLLM("{}", TokenUsage(prompt_tokens=5, completion_tokens=1)),
        tel,
    )
    await planner.plan("任意任务")
    assert tel.records == []
