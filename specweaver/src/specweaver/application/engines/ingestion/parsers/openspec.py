"""OpenSpec dialect parsers (repository profile ``openspec``).

OpenSpec layout (https://github.com/mddiosc/openspec-demo):

- ``openspec/specs/<capability>/spec.md`` — current requirements, one
  ``### Requirement:`` block each (plus ``#### Scenario:`` acceptance blocks);
- ``openspec/changes/<change>/specs/<capability>/spec.md`` — pending deltas
  grouped into ``## ADDED / ## MODIFIED / ## REMOVED Requirements`` sections;
- ``openspec/changes/<change>/{proposal,design,tasks}.md`` — change rationale
  (parsed by the default markdown parser as design artifacts);
- ``openspec/changes/archive/<change>/...`` — archived history: proposal/design
  stay indexed, archived delta sheets are skipped (they duplicate specs/).

Requirement identity is ``capability + requirement name``; the id is a
deterministic digest of that pair, so a pending MODIFIED delta can point its
``supersedes`` at the exact active requirement it replaces. Delta entries are
salted with the change id so a draft never collides with the active artifact.

Entries from one sheet share the sheet's file checksum: incrementality is
tracked per entry id, but at file granularity — that is inherent, since one
checksum covers the whole file.
"""

from __future__ import annotations

import hashlib
import re

from .....domain.enums import ArtifactType
from ..discovery import DiscoveredFile, DiscoveryReport, FileDiscovery
from ..taxonomy import classify_by_path, is_ignored
from .base import ParsedDocument
from .markdown import extract_refs

_REQ_HEADING_RE = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.M)
_DELTA_SECTION_RE = re.compile(
    r"^##\s+(ADDED|MODIFIED|REMOVED)\s+Requirements\s*$", re.M
)
_SCENARIO_RE = re.compile(r"^####\s+Scenario:\s*(.+?)\s*$", re.M)
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")

_DELTA_STATUS = {
    "ADDED": "draft",
    "MODIFIED": "draft",
    "REMOVED": "deprecated",
}

_NON_PY_EXTS = (".py", ".pyw")


def lowered(parts: list[str]) -> list[str]:
    return [p.lower() for p in parts]


def requirement_id(capability: str, name: str) -> str:
    """Deterministic active-requirement id from its OpenSpec identity."""
    digest = hashlib.sha1(
        f"{capability}|{name}".encode()
    ).hexdigest()[:12]
    return f"REQ-{digest}"


def _delta_id(capability: str, name: str, change: str) -> str:
    digest = hashlib.sha1(
        f"{capability}|{name}|{change}".encode()
    ).hexdigest()[:12]
    return f"REQ-{digest}"


def _norm(path: str) -> list[str]:
    return [p for p in path.replace("\\", "/").split("/") if p]


def classify_openspec(path: str) -> ArtifactType | None:
    """Type for OpenSpec-convention paths; None = skip (or defer to default).

    Returns None for archived delta sheets: their content is already merged
    into specs/ (or superseded by later changes), so re-ingesting them would
    mint stale duplicates.
    """
    parts = _norm(path)
    if not parts or parts[0].lower() != "openspec":
        return None
    lowered_parts = lowered(parts)
    if "changes" in lowered_parts:
        change_at = lowered_parts.index("changes")
        rest = lowered_parts[change_at + 1 :]
        if rest and rest[0] == "archive":
            if "specs" in rest[1:]:
                return None
            return (
                ArtifactType.design if path.lower().endswith(".md") else None
            )
        if "specs" in rest:
            return ArtifactType.requirement
        if path.lower().endswith(
            ("proposal.md", "design.md", "tasks.md")
        ):
            return ArtifactType.design
        return None
    if "specs" in lowered_parts:
        return ArtifactType.requirement
    if parts[-1].lower() in ("project.md", "config.yaml"):
        return ArtifactType.rule
    return None


def is_spec_sheet(path: str) -> bool:
    parts = _norm(path)
    return (
        len(parts) >= 3
        and parts[0].lower() == "openspec"
        and parts[1].lower() == "specs"
        and parts[-1].lower() == "spec.md"
    )


def is_delta_sheet(path: str) -> bool:
    parts = _norm(path)
    lowered_parts = lowered(parts)
    return (
        len(parts) >= 4
        and lowered_parts[0] == "openspec"
        and lowered_parts[1] == "changes"
        and lowered_parts[2] != "archive"
        and "specs" in lowered_parts[3:]
        and parts[-1].lower() == "spec.md"
    )


def is_non_python_code(path: str, declared_type: ArtifactType) -> bool:
    """Tier-2 matcher: code/test files the ast-based parsers cannot read."""
    if declared_type not in (ArtifactType.code, ArtifactType.test):
        return False
    return not path.lower().endswith(_NON_PY_EXTS)


_MODAL_RE = re.compile(r"\b(shall|must|should|will)\b", re.I)


def _behavior_and_summary(body: str) -> tuple[list[str], str]:
    behavior: list[str] = []
    summary_parts: list[str] = []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            continue
        item = _LIST_RE.match(line)
        if item:
            behavior.append(item.group(1).strip())
        elif line.strip():
            prose = line.strip()
            if len(summary_parts) < 3:
                summary_parts.append(prose)
            # OpenSpec states requirements as prose ("The system SHALL ...");
            # modal sentences are behavior points, not just summary fodder.
            if _MODAL_RE.search(prose) and prose not in behavior:
                behavior.append(prose)
    for match in _SCENARIO_RE.finditer(body):
        behavior.append(f"Scenario: {match.group(1).strip()}")
    return behavior, " ".join(summary_parts)[:400]


def _capability(parts: list[str], specs_at: int) -> str:
    if specs_at + 1 < len(parts):
        return parts[specs_at + 1]
    return "openspec"


class OpenSpecSpecParser:
    """Flattens ``openspec/specs/<cap>/spec.md`` into per-requirement docs."""

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> list[ParsedDocument]:
        parts = _norm(path)
        specs_at = next(
            (i for i, p in enumerate(lowered(parts)) if p == "specs"), 1
        )
        capability = _capability(parts, specs_at)

        matches = list(_REQ_HEADING_RE.finditer(text))
        if not matches:
            # No requirement blocks: keep the sheet searchable as one entry.
            title = next(
                (
                    line.lstrip("#").strip()
                    for line in text.splitlines()
                    if line.startswith("# ")
                ),
                parts[-2] if len(parts) >= 2 else path,
            )
            return [
                ParsedDocument(
                    path=path,
                    type=ArtifactType.requirement,
                    title=title,
                    summary=text.strip()[:400],
                    references=extract_refs(text),
                    front_matter={"module": capability, "status": "active"},
                    checksum=checksum,
                    raw_text=text,
                )
            ]

        docs: list[ParsedDocument] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(text)
            )
            name = match.group(1).strip()
            behavior, summary = _behavior_and_summary(text[start:end])
            docs.append(
                ParsedDocument(
                    path=path,
                    type=ArtifactType.requirement,
                    title=name,
                    summary=summary,
                    behavior_points=behavior,
                    references=extract_refs(text[start:end]),
                    front_matter={
                        "id": requirement_id(capability, name),
                        "module": capability,
                        "status": "active",
                        "capability": capability,
                    },
                    checksum=checksum,
                    raw_text=text,
                )
            )
        return docs


class OpenSpecDeltaParser:
    """Flattens pending ``changes/<change>/specs/<cap>/spec.md`` deltas.

    ADDED/MODIFIED become draft requirements (MODIFIED/REMOVED carry
    ``supersedes`` pointing at the active requirement id), REMOVED becomes a
    deprecated tombstone. ``RENAMED`` sections are not modeled in v1 and are
    skipped; the capability is read from the sheet's directory.
    """

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> list[ParsedDocument]:
        parts = _norm(path)
        lowered_parts = lowered(parts)
        change_at = lowered_parts.index("changes")
        change = parts[change_at + 1]
        specs_at = lowered_parts.index("specs", change_at)
        capability = _capability(parts, specs_at)

        sections = list(_DELTA_SECTION_RE.finditer(text))
        docs: list[ParsedDocument] = []
        for s_index, section in enumerate(sections):
            verb = section.group(1)
            section_end = (
                sections[s_index + 1].start()
                if s_index + 1 < len(sections)
                else len(text)
            )
            section_body = text[section.end() : section_end]
            reqs = list(_REQ_HEADING_RE.finditer(section_body))
            for r_index, req in enumerate(reqs):
                start = req.end()
                end = (
                    reqs[r_index + 1].start()
                    if r_index + 1 < len(reqs)
                    else len(section_body)
                )
                name = req.group(1).strip()
                behavior, summary = _behavior_and_summary(
                    section_body[start:end]
                )
                fm: dict = {
                    "id": _delta_id(capability, name, change),
                    "module": capability,
                    "status": _DELTA_STATUS[verb],
                    "capability": capability,
                    "tags": f"change:{change},delta:{verb.lower()}",
                }
                if verb in ("MODIFIED", "REMOVED"):
                    fm["supersedes"] = requirement_id(capability, name)
                docs.append(
                    ParsedDocument(
                        path=path,
                        type=ArtifactType.requirement,
                        title=name,
                        summary=summary,
                        behavior_points=behavior,
                        references=extract_refs(section_body[start:end]),
                        front_matter=fm,
                        checksum=checksum,
                        raw_text=text,
                    )
                )
        return docs


class OpenSpecFileDiscovery(FileDiscovery):
    """Classifies OpenSpec paths; everything else defers to the heuristics.

    Within ``openspec/`` the profile's own classification is final — a None
    (archived delta sheets, unknown files) means skipped, never a fallback to
    the generic heuristics, which would resurrect the sheets we exclude.
    """

    def discover(self, paths: list[str]) -> DiscoveryReport:
        files: list[DiscoveredFile] = []
        skipped: list[str] = []
        for path in paths:
            if is_ignored(path):
                skipped.append(path)
                continue
            if _norm(path)[0].lower() == "openspec":
                declared = classify_openspec(path)
            else:
                declared = classify_by_path(path)
            if declared is None:
                skipped.append(path)
                continue
            files.append(DiscoveredFile(path, declared))
        return DiscoveryReport(files=files, skipped=skipped)
