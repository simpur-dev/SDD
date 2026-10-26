"""Boundary battery for validity detectors and assembly budget accounting."""
from __future__ import annotations

from specweaver.application.engines.assembly.pipeline import AssemblyEngine
from specweaver.application.engines.assembly.render import render_json
from specweaver.application.engines.assembly.sections import map_sections
from specweaver.application.engines.retrieval.planner import (
    QueryPlanner,
    rule_keywords,
)
from specweaver.application.engines.validity.conflict import ConflictDetector
from specweaver.application.engines.validity.lifecycle import (
    LifecycleValidator,
)
from specweaver.application.engines.validity.suspect import SuspectDetector
from specweaver.domain.entities import Artifact, Task
from specweaver.domain.enums import ArtifactType


def _req(
    aid: str, module: str, content: str, **kw: object
) -> Artifact:
    return Artifact(
        id=aid,
        project_id="p",
        type=ArtifactType.requirement,
        module=module,
        title=aid,
        content=content,
        **kw,  # type: ignore[arg-type]
    )


async def test_conflict_requires_distinct_artifacts() -> None:
    a = _req("REQ-1", "schedule", "- 间隔不得低于 5 分钟\n")
    b = _req("DES-9", "schedule", "- 间隔不得低于 3 分钟\n")
    b = b.model_copy(update={"type": ArtifactType.rule})
    findings = await ConflictDetector().detect([a, b])
    assert len(findings) == 1
    same = _req("REQ-2", "schedule", "- 间隔不得低于 5 分钟\n")
    assert await ConflictDetector().detect([a, same]) == []


async def test_conflict_detects_fullwidth_digits() -> None:
    """re \\d is unicode-aware: ５ and 5 are distinct numeric values."""
    a = _req("REQ-1", "schedule", "- 间隔不得低于 5 分钟\n")
    b = _req("REQ-2", "schedule", "- 间隔不得低于 ５ 分钟\n")
    findings = await ConflictDetector().detect([a, b])
    assert len(findings) == 1


async def test_suspect_flags_dangling_reference() -> None:
    """Audit B5 fixed: a reference to a missing upstream is a finding."""
    downstream = _req("REQ-9", "api", "- x\n")
    downstream = downstream.model_copy(
        update={"type": ArtifactType.code, "based_on": ["REQ-404"]}
    )

    class _Miss:
        async def get_artifact(self, project_id: str, artifact_id: str):
            return None

    findings = await SuspectDetector(_Miss()).detect([downstream])
    assert len(findings) == 1
    assert "missing from the catalog" in findings[0].message


def test_applies_to_ref_matches_whole_segments() -> None:
    """Audit B1 fixed: segment equality, not substring."""
    art = _req(
        "REQ-1", "m", "c",
        applies_to_ref="release/1.20",
    )
    assert LifecycleValidator().validate(
        art, current_ref="1.2"
    ).valid is False
    assert LifecycleValidator().validate(
        art, current_ref="release/1.20"
    ).valid is True
    multi = _req("REQ-2", "m", "c", applies_to_ref="main, release/1.2")
    assert LifecycleValidator().validate(
        multi, current_ref="release/1.2"
    ).valid is True


async def test_budget_under_chrome_is_disclosed() -> None:
    """Audit C3 fixed: chrome-over-budget stays honest AND loudly disclosed."""
    from specweaver.application.engines.assembly import render_markdown

    task = Task(id="t", project_id="p", title="t")
    art = _req("REQ-1", "m", "- 约束一\n" + "内" * 200)
    bundle = await AssemblyEngine(max_bytes=100).run(task, [art], [])
    assert bundle.budget is not None
    assert bundle.budget.truncated is True
    assert "exceeds this budget" in render_markdown(bundle)


async def test_bundle_json_drops_embeddings() -> None:
    """Audit B-7: render_json serialises 1536-float embeddings per artifact;
    demo evidence 02-context.json is 604 KB of which ~all is vectors.
    """
    task = Task(id="t", project_id="p", title="t")
    art = _req("REQ-1", "m", "- c\n")
    art = art.model_copy(update={"embedding": [0.5] * 1536})
    bundle = await AssemblyEngine(8000).run(task, [art], [])
    payload = render_json(bundle)
    assert payload.encode().count(b"0.5") < 16


def test_rule_keywords_bounds() -> None:
    assert rule_keywords("") == []
    many = rule_keywords(" ".join(f"word{i}" for i in range(50)))
    assert len(many) == 16


async def test_planner_empty_task_falls_back() -> None:
    plan = await QueryPlanner(None).plan("")
    assert plan.keywords == []
    assert plan.rationale == "rule-based planning"


async def test_empty_task_short_circuits_before_backend() -> None:
    """Audit B-16 guard: a blank task must never reach hybrid search."""
    from fakes.inference import ScriptedEmbedding

    from specweaver.application.engines.retrieval import RetrievalEngine

    class _Boom:
        async def hybrid_search(self, query):  # pragma: no cover
            raise AssertionError("backend must not be hit for empty task")

    engine = RetrievalEngine(QueryPlanner(None), ScriptedEmbedding(8), _Boom())
    result = await engine.run("p", "   ")
    assert result.scored == []
    assert result.plan.objective == "   "


def test_sections_sorted_rule_before_requirement() -> None:
    rule = _req("RULE-1", "m", "r")
    rule = rule.model_copy(update={"type": ArtifactType.rule})
    req = _req("REQ-2", "m", "r")
    sections = map_sections([req, rule])
    assert [a.id for a in sections.goal_and_constraints] == [
        "RULE-1",
        "REQ-2",
    ]
