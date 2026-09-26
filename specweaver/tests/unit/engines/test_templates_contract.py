"""The shipped SDD templates must match what ingestion actually digests.

Two directions are pinned here: the template front matter only promises keys the
parser reads, and a real corpus file (demo/railway) parsed by the production
parser stays inside the shape the template declares. Without this test the
templates in specweaver/templates/ would be decorative.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from specweaver.application.engines.ingestion.normalize import artifact_id
from specweaver.application.engines.ingestion.parsers.markdown import (
    MarkdownParser,
    split_front_matter,
)
from specweaver.application.engines.ingestion.taxonomy import normalize_type
from specweaver.domain.enums import ArtifactType

PKG_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = PKG_ROOT / "templates"
RAILWAY = PKG_ROOT.parent / "demo" / "railway"

PARSER = MarkdownParser()

# template -> (declared ArtifactType, corpus instance, normalised artifact id,
# fields a file of this shape must yield)
CASES = {
    "constitution.md": (
        ArtifactType.rule,
        RAILWAY / "rules" / "interval-rule.md",
        "RULE-1",
        ("constraints",),
    ),
    "spec-template.md": (
        ArtifactType.requirement,
        RAILWAY / "specs" / "requirement-schedule.md",
        "REQ-1",
        ("behavior_points", "constraints"),
    ),
    "plan-template.md": (
        ArtifactType.design,
        RAILWAY / "design" / "schedule-design.md",
        "DES-1",
        ("references", "summary"),
    ),
}
WORK_PRODUCT_TEMPLATES = ("tasks-template.md", "checklist-template.md")


@pytest.mark.parametrize("name", sorted(CASES))
def test_template_declares_consumable_front_matter(name: str) -> None:
    front, _ = split_front_matter(
        (TEMPLATES / name).read_text(encoding="utf-8")
    )

    expected_type = CASES[name][0]
    assert normalize_type(front.get("type")) is expected_type
    # these four keys are the only front-matter keys read anywhere in ingestion
    assert {"id", "type", "title", "module"} <= set(front)
    assert set(front) <= {
        "id", "type", "title", "module", "version", "status"
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_corpus_instance_stays_inside_the_declared_shape(name: str) -> None:
    expected_type, instance, expected_id, expected_fields = CASES[name]
    template_front, _ = split_front_matter(
        (TEMPLATES / name).read_text(encoding="utf-8")
    )
    text = instance.read_text(encoding="utf-8")
    front, _ = split_front_matter(text)
    doc = PARSER.parse(
        str(instance.relative_to(RAILWAY.parent)),
        text,
        checksum=None,
        declared_type=expected_type,
    )

    assert set(front) <= set(template_front)
    assert doc.type is expected_type
    assert artifact_id(doc) == expected_id  # REQ-01 -> REQ-1
    assert doc.front_matter["module"]
    for field in expected_fields:
        assert getattr(doc, field), f"{name} shape must yield {field}"


def test_work_product_templates_are_not_ingested() -> None:
    """tasks/checklist guide the Agent but carry no id, so they must not be
    mistaken for catalog artifacts."""
    for name in WORK_PRODUCT_TEMPLATES:
        front, _ = split_front_matter(
            (TEMPLATES / name).read_text(encoding="utf-8")
        )
        assert front == {}


def test_templates_are_shipped_with_the_package() -> None:
    assert {path.name for path in TEMPLATES.glob("*.md")} == {
        *CASES,
        *WORK_PRODUCT_TEMPLATES,
        "README.md",
    }
