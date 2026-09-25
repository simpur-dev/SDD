from __future__ import annotations

from dataclasses import dataclass

from ....domain.enums import ArtifactType
from .taxonomy import classify_by_path, is_ignored


@dataclass(frozen=True)
class DiscoveredFile:
    path: str
    type: ArtifactType


@dataclass(frozen=True)
class DiscoveryReport:
    files: list[DiscoveredFile]
    skipped: list[str]


class FileDiscovery:
    """Select and classify project files without reading their content."""

    def discover(self, paths: list[str]) -> DiscoveryReport:
        files: list[DiscoveredFile] = []
        skipped: list[str] = []
        for path in paths:
            if is_ignored(path):
                skipped.append(path)
                continue
            artifact_type = classify_by_path(path)
            if artifact_type is None:
                skipped.append(path)
                continue
            files.append(DiscoveredFile(path=path, type=artifact_type))
        return DiscoveryReport(files=files, skipped=skipped)
