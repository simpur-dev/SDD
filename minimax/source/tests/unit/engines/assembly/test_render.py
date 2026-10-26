from __future__ import annotations

from datetime import datetime

from specweaver.application.engines.assembly import (
    entry_block,
    render_markdown,
)
from specweaver.domain.entities import (
    Artifact,
    ContextBundle,
    Task,
    TestRun,
)
from specweaver.domain.enums import (
    ArtifactType,
    FindingKind,
    LifecycleStatus,
    Severity,
)
from specweaver.domain.values import Budget, Finding, SourceRef


def _bundle() -> ContextBundle:
    task = Task(id="task-1", project_id="p", title="按站调整")
    req = Artifact(
        id="REQ-1",
        project_id="p",
        type=ArtifactType.requirement,
        title="需求",
        content="- 应能调整发车时间",
        source=SourceRef(uri="specs/req.md", locator="L3"),
    )
    code = Artifact(
        id="CODE-1",
        project_id="p",
        type=ArtifactType.code,
        title="schedule",
        content="def adjust():\n    return\n\ndef other():\n    return\n",
    )
    finding = Finding(
        kind=FindingKind.conflict,
        severity=Severity.critical,
        message="约束矛盾",
        refs=[],
        needs_confirmation=True,
    )
    return ContextBundle(
        task=task,
        goal_and_constraints=[req],
        design_and_implementation=[code],
        verification=[],
        findings=[finding],
        budget=Budget(max_bytes=8000, used_bytes=123),
        generated_at=datetime(2026, 9, 25),
    )


def test_markdown_has_six_sections_and_citation() -> None:
    markdown = render_markdown(_bundle())
    for marker in ["①", "②", "③", "④", "⑤", "⑥"]:
        assert marker in markdown
    assert "REQ-1" in markdown
    assert "specs/req.md" in markdown
    assert "needs confirmation" in markdown


def test_code_entry_is_summarized() -> None:
    code = Artifact(
        id="CODE-1",
        project_id="p",
        type=ArtifactType.code,
        title="schedule",
        content="def adjust():\n    pass\n" * 20,
        status=LifecycleStatus.active,
    )
    block = entry_block(code)
    assert "full source" in block
    assert "def adjust" in block


def test_citation_locator_has_no_stray_dollar() -> None:
    markdown = render_markdown(_bundle())
    assert "#$L3" not in markdown
    assert "#L3" in markdown


def test_truncated_budget_emits_warning() -> None:
    bundle = _bundle()
    bundle.budget = Budget(
        max_bytes=8000, used_bytes=8000, truncated=True
    )
    markdown = render_markdown(bundle)
    assert "truncated to budget" in markdown


def test_last_test_run_rendered_in_verification_section() -> None:
    bundle = _bundle()
    bundle.last_test_run = TestRun(
        id="tr-1",
        task_id="task-9",
        command="pytest",
        total=5,
        passed=5,
        failed=0,
        commit_ref="abc123",
    )
    markdown = render_markdown(bundle)
    verification = markdown.split("## ③")[1].split("## ④")[0]
    assert "last test run [PASS]" in verification
    assert "task-9" in verification
    assert "ref=abc123" in verification
