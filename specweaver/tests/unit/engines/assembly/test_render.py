from __future__ import annotations

from datetime import datetime

from specweaver.application.engines.assembly import (
    entry_block,
    render_markdown,
)
from specweaver.domain.entities import Artifact, ContextBundle, Task
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
