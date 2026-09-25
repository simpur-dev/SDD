from __future__ import annotations

import re

from ....domain.entities import Artifact
from ....domain.enums import ArtifactType, FindingKind, Severity
from ....domain.values import Finding
from .citations import cite

_LIST_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_NEG_RE = re.compile(r"禁止|不得|严禁|不能|must not|shall not")
_MODAL_RE = re.compile(
    r"禁止|不得|严禁|不能|必须|应当|应该|允许|可以|须|应"
)
_PUNCT_RE = re.compile(r"[，,。；;：:、\s]+")


def _constraint_lines(artifact: Artifact) -> list[str]:
    return _LIST_RE.findall(artifact.content)


def _subject(line: str) -> str:
    """Normalize a constraint to its subject by masking values, modals and punctuation."""
    masked = _MODAL_RE.sub("~", _NUM_RE.sub("#", line))
    masked = re.sub(r"~+", "~", masked)
    return _PUNCT_RE.sub("", masked)


def _numbers(line: str) -> tuple[str, ...]:
    return tuple(sorted(set(_NUM_RE.findall(line))))


def _polarity(line: str) -> str:
    return "neg" if _NEG_RE.search(line) else "pos"


class _Cell:
    __slots__ = ("numbers", "polarity", "artifact", "example")

    def __init__(self, numbers, polarity, artifact, example) -> None:
        self.numbers = numbers
        self.polarity = polarity
        self.artifact = artifact
        self.example = example


class ConflictDetector:
    """Detects contradictory active requirements/rules within the same module.

    A conflict requires the same constraint subject in two distinct artifacts
    plus either different required numeric values or opposite polarity; this
    deliberately avoids speculative semantic-conflict claims.
    """

    async def detect(self, artifacts: list[Artifact]) -> list[Finding]:
        groups: dict[str, list[Artifact]] = {}
        for artifact in artifacts:
            if artifact.type not in (
                ArtifactType.requirement,
                ArtifactType.rule,
            ):
                continue
            key = artifact.module or "(root)"
            groups.setdefault(key, []).append(artifact)

        findings: list[Finding] = []
        for module, members in groups.items():
            index: dict[str, dict[str, _Cell]] = {}
            for artifact in members:
                for line in _constraint_lines(artifact):
                    subject = _subject(line)
                    if not subject:
                        continue
                    cell = _Cell(
                        _numbers(line),
                        _polarity(line),
                        artifact,
                        line.strip(),
                    )
                    table = index.setdefault(subject, {})
                    current = table.get(artifact.id)
                    if current is None or (
                        cell.numbers and not current.numbers
                    ):
                        table[artifact.id] = cell

            for table in index.values():
                cells = list(table.values())
                if len({cell.artifact.id for cell in cells}) < 2:
                    continue
                number_sets = {cell.numbers for cell in cells if cell.numbers}
                polarities = {cell.polarity for cell in cells}
                polarity_clash = len(polarities) >= 2
                numeric_clash = len(number_sets) >= 2
                if not (polarity_clash or numeric_clash):
                    continue
                involved = _unique_artifacts(cells)
                findings.append(
                    Finding(
                        kind=FindingKind.conflict,
                        severity=Severity.critical
                        if polarity_clash
                        else Severity.warning,
                        message=(
                            f"Conflicting constraints in module '{module}': "
                            f"{cells[0].example}"
                        ),
                        refs=[cite(artifact) for artifact in involved],
                        suggestion=(
                            "Confirm the authoritative constraint before "
                            "editing this area."
                        ),
                        needs_confirmation=True,
                    )
                )
        return findings


def _unique_artifacts(cells: list[_Cell]) -> list[Artifact]:
    out: list[Artifact] = []
    seen: set[str] = set()
    for cell in cells:
        if cell.artifact.id not in seen:
            seen.add(cell.artifact.id)
            out.append(cell.artifact)
    return out
