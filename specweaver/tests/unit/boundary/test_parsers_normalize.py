"""Boundary battery for parsers, normalize and taxonomy.

Failures here are audit findings (docs: M4 boundary audit), each pinned by
executable evidence.
"""
from __future__ import annotations

import pytest

from specweaver.application.engines.ingestion.normalize import (
    artifact_id,
    to_artifact,
)
from specweaver.application.engines.ingestion.parsers.base import (
    ParsedDocument,
)
from specweaver.application.engines.ingestion.parsers.markdown import (
    MarkdownParser,
    extract_refs,
    split_front_matter,
)
from specweaver.application.engines.ingestion.parsers.python_code import (
    PythonCodeParser,
)
from specweaver.application.engines.ingestion.taxonomy import (
    classify_by_path,
)
from specweaver.domain.enums import ArtifactType


def _doc(path: str, text: str) -> ParsedDocument:
    return MarkdownParser().parse(
        path, text, "sha256:x", ArtifactType.requirement
    )


def test_unclosed_front_matter_is_ignored_as_text() -> None:
    fm, body = split_front_matter("---\nid: REQ-1\nno closing")
    assert fm == {}
    assert "id: REQ-1" in body


def test_crlf_front_matter_parses() -> None:
    doc = _doc("specs/a.md", "---\r\nid: REQ-01\r\ntype: requirement\r\n---\r\n# t\r\n")
    assert artifact_id(doc) == "REQ-1"


@pytest.mark.xfail(strict=True, reason="audit B-1: BOM drops front-matter")
def test_bom_prefixed_front_matter_still_parsed() -> None:
    """Audit B-1: BOM is common on Windows; front-matter must not be lost."""
    doc = _doc("design/x.md", "﻿---\nid: DES-01\ntype: design\n---\n# t\n")
    assert artifact_id(doc) == "DES-1"


def test_quoted_and_colon_values_in_front_matter() -> None:
    fm, _ = split_front_matter(
        '---\ntitle: "My: Spec"\nmodule: schedule\n---\nbody'
    )
    assert fm["title"] == "My: Spec"
    assert fm["module"] == "schedule"


def test_refs_reject_overlong_numbers() -> None:
    # documented limitation: 6+ digit ids are silently ignored (cap \d{1,5})
    assert extract_refs("REQ-123456 DES-9876543") == []


def test_refs_are_case_sensitive_and_pad_zero() -> None:
    # REQ-000005 is 6 digits -> out of the \d{1,5} cap; lowercase rule-3 is
    # not matched (extract_refs is uppercase-only). Both are documented
    # limitations pinned here so a future regex change is a deliberate act.
    assert extract_refs("REQ-0005") == ["REQ-5"]
    assert extract_refs("REQ-000005 rule-3") == []


def test_python_syntax_error_file_is_indexed_without_symbols() -> None:
    doc = PythonCodeParser().parse(
        "src/broken.py", "def broken(:\n", "sha256:y", ArtifactType.code
    )
    assert doc.symbols == []
    assert doc.raw_text.startswith("def broken(")


def test_duplicate_explicit_ids_map_to_same_artifact_id() -> None:
    """Audit B-2: two files with id REQ-01 collide silently (last upsert wins)."""
    a = _doc("specs/a.md", "---\nid: REQ-01\n---\n# A\n")
    b = _doc("specs/b.md", "---\nid: REQ-01\n---\n# B\n")
    art_a = to_artifact("p", a)
    art_b = to_artifact("p", b)
    assert art_a.id == art_b.id == "REQ-1"  # no duplicate detection hook


def test_classify_path_boundaries() -> None:
    assert classify_by_path("docs/architecture.md") is ArtifactType.design
    assert classify_by_path("rules/const.md") is ArtifactType.rule
    assert classify_by_path("tests/test_api.py") is ArtifactType.test
    assert classify_by_path("src/main.rs") is ArtifactType.code
    assert classify_by_path("pyproject.toml") is None
