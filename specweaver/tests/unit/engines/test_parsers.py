from __future__ import annotations

from specweaver.application.engines.ingestion.parsers import (
    MarkdownParser,
    PythonCodeParser,
    PythonTestParser,
)
from specweaver.domain.enums import ArtifactType

REQUIREMENT_MD = """---
id: REQ-0001
title: 按站调整发车时间
version: 1.0.0
---
# 按站调整发车时间

## 验收条件
- 调度员应能按站修改发车时间
- 不得影响后续区间占用

相关设计见 DES-0002。
"""

CODE = '''"""调度模块。"""
from occupancy import Occupancy


class Schedule:
    """列车计划。"""

    def adjust(self, train_id, station):
        """调整发车 @implements REQ-0001"""
        return 1


def publish(plan):
    return plan
'''

TEST = '''def test_adjust():
    """@covers REQ-0001"""
    assert True
'''


def test_requirement_markdown() -> None:
    doc = MarkdownParser().parse(
        "specs/req.md", REQUIREMENT_MD, "chk", ArtifactType.requirement
    )
    assert doc.type is ArtifactType.requirement
    assert doc.title == "按站调整发车时间"
    assert any("按站修改" in point for point in doc.behavior_points)
    assert any("不得" in point for point in doc.constraints)
    assert "DES-2" in doc.references
    assert doc.front_matter["version"] == "1.0.0"


def test_front_matter_type_overrides_path() -> None:
    text = "---\ntype: design\n---\n# 标题\n"
    doc = MarkdownParser().parse(
        "notes/x.md", text, "chk", ArtifactType.requirement
    )
    assert doc.type is ArtifactType.design


def test_python_code_parser() -> None:
    doc = PythonCodeParser().parse(
        "railway/schedule.py", CODE, "chk", ArtifactType.code
    )
    names = [symbol.name for symbol in doc.symbols]
    assert "Schedule" in names
    assert "Schedule.adjust" in names
    assert "publish" in names
    kinds = {s.name: s.kind for s in doc.symbols}
    assert kinds["Schedule"] == "class"
    assert kinds["Schedule.adjust"] == "method"
    assert kinds["publish"] == "function"
    assert "REQ-1" in doc.references
    assert "occupancy" in doc.imports
    assert doc.summary == "调度模块。"


def test_python_test_parser() -> None:
    doc = PythonTestParser().parse(
        "tests/test_schedule.py", TEST, "chk", ArtifactType.test
    )
    assert doc.type is ArtifactType.test
    assert [symbol.name for symbol in doc.symbols] == ["test_adjust"]
    assert doc.symbols[0].kind == "test_case"
    assert doc.front_matter["test_target_module"] == "schedule"
    assert "REQ-1" in doc.references


def test_python_code_tolerates_syntax_error() -> None:
    doc = PythonCodeParser().parse(
        "railway/broken.py", "def broken(:\n", "chk", ArtifactType.code
    )
    assert doc.symbols == []
    assert doc.imports == []
    assert doc.raw_text  # retained so the file is still keyword-searchable


def test_python_code_tolerates_empty_file() -> None:
    doc = PythonCodeParser().parse(
        "railway/empty.py", "", "chk", ArtifactType.code
    )
    assert doc.symbols == []
    assert doc.title == "empty"


def test_markdown_without_front_matter_uses_heading() -> None:
    doc = MarkdownParser().parse(
        "specs/req.md", "# 需求标题\n\n- 应能工作\n", "chk",
        ArtifactType.requirement,
    )
    assert doc.title == "需求标题"
    assert doc.type is ArtifactType.requirement


def test_markdown_empty_file_falls_back_to_stem() -> None:
    doc = MarkdownParser().parse(
        "specs/req.md", "", "chk", ArtifactType.requirement
    )
    assert doc.title == "req"
    assert doc.behavior_points == []


def test_markdown_unclosed_front_matter_is_body() -> None:
    doc = MarkdownParser().parse(
        "specs/req.md", "---\nid: REQ-1\nno closing fence\n", "chk",
        ArtifactType.requirement,
    )
    assert doc.front_matter == {}


def test_python_test_without_cases() -> None:
    doc = PythonTestParser().parse(
        "tests/conftest.py", "import pytest\n", "chk", ArtifactType.test
    )
    assert doc.type is ArtifactType.test
    assert doc.symbols == []
    assert doc.behavior_points == []
