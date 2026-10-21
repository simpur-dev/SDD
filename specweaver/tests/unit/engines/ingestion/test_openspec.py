"""Golden-sample tests for the openspec profile and the tier-2 parser."""

from __future__ import annotations

import copy

from fakes.catalog import InMemoryCatalog
from fakes.inference import ScriptedEmbedding
from fakes.workspace import InMemoryWorkspace

from specweaver.application.engines.ingestion import IngestionEngine
from specweaver.application.engines.ingestion.parsers.openspec import (
    OpenSpecDeltaParser,
    OpenSpecSpecParser,
    classify_openspec,
    is_spec_sheet,
    requirement_id,
)
from specweaver.application.engines.ingestion.parsers.text_symbols import (
    TextSymbolsParser,
)
from specweaver.application.engines.ingestion.profiles import resolve_profile
from specweaver.application.usecases.ingest_project import (
    IngestProject,
    IngestProjectRequest,
)
from specweaver.domain.enums import ArtifactType
from specweaver.shared.telemetry import Telemetry

SPEC_MD = """# search Specification

## Purpose
Enable users to search books by author.

### Requirement: Filter search results
The system SHALL filter results by author.

#### Scenario: filter by author
- **WHEN** the user picks an author
- **THEN** only matching books are listed

### Requirement: Paginate results
The system SHALL paginate result pages.
"""

DELTA_MD = """## ADDED Requirements

### Requirement: Sort results
The system SHALL sort results by title.

## MODIFIED Requirements

### Requirement: Filter search results
The system SHALL filter results by author AND year.

## REMOVED Requirements

### Requirement: Paginate results
"""

TS_CODE = """import { searchBooks } from "./search";

export interface Book {
  id: string;
}

export function filterBooks(books: Book[], author: string): Book[] {
  return books.filter((b) => b.author === author);
}

export const sortBooks = (books: Book[]): Book[] => books;
"""

TS_TEST = """import { describe, it, expect } from "vitest";
import { filterBooks } from "../src/filter-search";

describe("filterBooks", () => {
  it("keeps matching authors", () => {
    expect(true).toBeTruthy();
  });
});
"""

TREE = {
    "openspec/specs/search/spec.md": SPEC_MD,
    "openspec/changes/add-sort/specs/search/spec.md": DELTA_MD,
    "openspec/changes/add-sort/proposal.md": "# Proposal\n\nAdd sorting.\n",
    "openspec/project.md": "# Project rules\n\n- Commits must pass tests.\n",
    "openspec/changes/archive/old-change/specs/search/spec.md": SPEC_MD,
    "openspec/changes/archive/old-change/proposal.md": "# Old\n",
    "src/search.ts": TS_CODE,
    "src/filter-search.ts": (
        'import { Book } from "./search";\n\n'
        "export function filterBooks(books: Book[], author: string): Book[] {\n"
        "  return books.filter((b) => b.author === author);\n}\n"
    ),
    "src/filter-search.spec.ts": TS_TEST,
}


def test_spec_sheet_flattens_per_requirement() -> None:
    docs = OpenSpecSpecParser().parse(
        "openspec/specs/search/spec.md", SPEC_MD, "sha", ArtifactType.requirement
    )
    assert [d.title for d in docs] == [
        "Filter search results",
        "Paginate results",
    ]
    assert all(d.type is ArtifactType.requirement for d in docs)
    assert docs[0].front_matter["module"] == "search"
    assert docs[0].front_matter["status"] == "active"
    assert docs[0].front_matter["id"] == requirement_id(
        "search", "Filter search results"
    )
    assert any("SHALL filter" in p for p in docs[0].behavior_points)
    assert any("Scenario: filter by author" in p for p in docs[0].behavior_points)


def test_requirement_ids_are_deterministic() -> None:
    first = OpenSpecSpecParser().parse(
        "openspec/specs/search/spec.md", SPEC_MD, None, ArtifactType.requirement
    )
    second = OpenSpecSpecParser().parse(
        "openspec/specs/search/spec.md", SPEC_MD, None, ArtifactType.requirement
    )
    assert [d.front_matter["id"] for d in first] == [
        d.front_matter["id"] for d in second
    ]


def test_delta_sections_map_to_status_and_supersedes() -> None:
    docs = OpenSpecDeltaParser().parse(
        "openspec/changes/add-sort/specs/search/spec.md",
        DELTA_MD,
        "sha",
        ArtifactType.requirement,
    )
    by_title = {d.title: d for d in docs}
    assert set(by_title) == {"Sort results", "Filter search results",
                             "Paginate results"}

    added = by_title["Sort results"]
    assert added.front_matter["status"] == "draft"
    assert "supersedes" not in added.front_matter
    assert "change:add-sort" in added.front_matter["tags"]
    assert "delta:added" in added.front_matter["tags"]

    modified = by_title["Filter search results"]
    assert modified.front_matter["status"] == "draft"
    assert modified.front_matter["supersedes"] == requirement_id(
        "search", "Filter search results"
    )

    removed = by_title["Paginate results"]
    assert removed.front_matter["status"] == "deprecated"
    assert removed.front_matter["supersedes"] == requirement_id(
        "search", "Paginate results"
    )

    # salted: a draft never collides with the active requirement id
    assert modified.front_matter["id"] != modified.front_matter["supersedes"]


def test_spec_parser_dedupes_duplicate_names_keep_first() -> None:
    """Same-named requirements share one identity hash; keeping the first
    keeps fresh and incremental ingests converged (last-wins diverges:
    a fresh catalog gets the last block, an incremental one keeps the
    first upsert)."""
    text = (
        "# search Specification\n\n"
        "### Requirement: Dup target\nThe system SHALL keep the first block.\n\n"
        "### Requirement: Dup target\nThe system SHALL never surface this block.\n"
    )
    docs = OpenSpecSpecParser().parse(
        "openspec/specs/search/spec.md", text, None, ArtifactType.requirement
    )
    assert len(docs) == 1
    assert any("keep the first block" in p for p in docs[0].behavior_points)
    assert not any("never surface" in p for p in docs[0].behavior_points)


def test_delta_parser_dedupes_same_name_across_sections() -> None:
    text = (
        "## ADDED Requirements\n\n"
        "### Requirement: Twice\nFirst delta body SHALL win.\n\n"
        "## MODIFIED Requirements\n\n"
        "### Requirement: Twice\nSecond body SHALL lose.\n"
    )
    docs = OpenSpecDeltaParser().parse(
        "openspec/changes/c1/specs/search/spec.md", text, None,
        ArtifactType.requirement,
    )
    assert len(docs) == 1
    assert docs[0].front_matter["status"] == "draft"
    assert "delta:added" in docs[0].front_matter["tags"]
    assert "supersedes" not in docs[0].front_matter


def test_malformed_spec_sheet_without_capability_falls_back() -> None:
    # openspec/specs/spec.md names no capability: not a spec sheet (a
    # capability of "spec.md" would be nonsense); classify still marks it
    # requirement so the generic markdown parser keeps it searchable.
    assert is_spec_sheet("openspec/specs/spec.md") is False
    assert is_spec_sheet("openspec/specs/search/spec.md") is True
    assert classify_openspec("openspec/specs/spec.md") is (
        ArtifactType.requirement
    )


def test_classify_openspec_paths() -> None:
    assert classify_openspec("openspec/specs/search/spec.md") is (
        ArtifactType.requirement
    )
    assert classify_openspec(
        "openspec/changes/add-sort/specs/search/spec.md"
    ) is ArtifactType.requirement
    assert classify_openspec(
        "openspec/changes/add-sort/proposal.md"
    ) is ArtifactType.design
    assert classify_openspec("openspec/project.md") is ArtifactType.rule
    # archived deltas are skipped; archived proposals stay indexed
    assert classify_openspec(
        "openspec/changes/archive/old/specs/search/spec.md"
    ) is None
    assert classify_openspec(
        "openspec/changes/archive/old/proposal.md"
    ) is ArtifactType.design
    assert classify_openspec("src/main.ts") is None  # deferred to heuristics


def test_text_symbols_extracts_ts_symbols_and_imports() -> None:
    doc = TextSymbolsParser().parse(
        "src/search.ts", TS_CODE, "sha", ArtifactType.code
    )[0]
    names = {s.name: s.kind for s in doc.symbols}
    assert names["filterBooks"] == "function"
    assert names["Book"] == "class"
    assert names["sortBooks"] == "function"  # const arrow slot
    assert doc.imports == ["search"]  # './search' normalized to the stem
    assert doc.type is ArtifactType.code


def test_text_symbols_recognizes_playwright_style_tests() -> None:
    doc = TextSymbolsParser().parse(
        "src/filter-search.spec.ts", TS_TEST, "sha", ArtifactType.code
    )[0]
    assert doc.type is ArtifactType.test
    assert doc.front_matter["test_target_module"] == "filter-search"
    assert doc.behavior_points == ["keeps matching authors"]
    assert all(s.kind == "test_case" for s in doc.symbols)


def _project(catalog, workspace):
    engine = IngestionEngine(ScriptedEmbedding(dim=8))
    return IngestProject(
        engine, catalog, workspace, Telemetry()
    )


async def test_openspec_profile_end_to_end() -> None:
    catalog = InMemoryCatalog()
    workspace = InMemoryWorkspace(copy.deepcopy(TREE))
    report = await _project(catalog, workspace)(
        IngestProjectRequest(project_id="demo", profile="openspec")
    )
    assert report.profile == "openspec"

    stored = {a.id: a for a in catalog.artifacts.values()}
    active_id = requirement_id("search", "Filter search results")
    assert active_id in stored  # per-requirement granularity from specs/
    assert stored[active_id].module == "search"

    # delta drafts present with supersedes; archive delta minted no artifact
    draft_ids = [
        a.id
        for a in stored.values()
        if a.status.value == "draft"
    ]
    assert len(draft_ids) == 2  # ADDED + MODIFIED
    superseded_target = next(
        a for a in stored.values() if a.supersedes == active_id
    )
    assert superseded_target.status.value == "draft"
    assert not any(
        a.source.uri
        and a.source.uri.startswith("openspec/changes/archive/old-change/specs")
        for a in stored.values()
    )

    # proposal/project.md ingested via markdown/rules classification
    assert any(
        a.type.value == "design"
        and a.source.uri == "openspec/changes/add-sort/proposal.md"
        for a in stored.values()
    )
    assert any(a.type.value == "rule" for a in stored.values())

    # ts code + test ingested through tier-2 with the naming edge
    code = next(a for a in stored.values() if a.source.uri == "src/search.ts")
    test = next(
        a for a in stored.values() if a.source.uri == "src/filter-search.spec.ts"
    )
    assert code.type.value == "code" and test.type.value == "test"
    edge = {(r.src, r.dst, r.kind.value) for r in catalog.relations}
    filter_code = next(
        a for a in stored.values() if a.source.uri == "src/filter-search.ts"
    )
    assert (test.id, filter_code.id, "tests") in edge


async def test_auto_sniff_picks_openspec_layout() -> None:
    workspace = InMemoryWorkspace(copy.deepcopy(TREE))
    profile = await resolve_profile(workspace, requested="", configured="auto")
    assert profile.name == "openspec"
