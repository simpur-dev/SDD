from __future__ import annotations

from specweaver.application.engines.ingestion.taxonomy import (
    classify_by_path,
    is_ignored,
    normalize_type,
)
from specweaver.domain.enums import ArtifactType


def test_classify_tests() -> None:
    assert classify_by_path("tests/test_schedule.py") is ArtifactType.test
    assert classify_by_path("app/schedule_test.py") is ArtifactType.test
    assert classify_by_path("tests/conftest.py") is ArtifactType.test


def test_classify_code() -> None:
    assert classify_by_path("railway/schedule.py") is ArtifactType.code
    assert classify_by_path("src/main.java") is ArtifactType.code


def test_classify_markdown() -> None:
    assert (
        classify_by_path("specs/requirements/train-schedule.md")
        is ArtifactType.requirement
    )
    assert (
        classify_by_path("docs/design/architecture.md") is ArtifactType.design
    )
    assert classify_by_path("constitution.md") is ArtifactType.rule


def test_unknown_markdown_and_binary() -> None:
    assert classify_by_path("LICENSE") is None
    assert classify_by_path("image.png") is None


def test_ignored_paths() -> None:
    assert is_ignored(".venv/lib/x.py")
    assert is_ignored("a/__pycache__/x.pyc")
    assert is_ignored(".github/workflows/ci.yml")


def test_normalize_front_matter_type() -> None:
    assert normalize_type("Requirements") is ArtifactType.requirement
    assert normalize_type("ADR") is ArtifactType.design
    assert normalize_type("constitution") is ArtifactType.rule
    assert normalize_type(None) is None
