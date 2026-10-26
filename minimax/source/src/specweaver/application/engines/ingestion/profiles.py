"""Repository profiles: per-repository ingestion policy.

A profile is pure strategy — it selects which parsers handle which files and
which files are discovered at all. It never performs IO itself: the engine
consumes the registry/discovery a profile provides, and every read/write still
flows through the same domain ports, so switching profiles never touches the
downstream engines, the Artifact model, or the seekdb physical layout.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ....domain.ports.workspace import WorkspacePort
from ....shared.errors import InvalidRequest
from .discovery import FileDiscovery
from .parsers import ParserRegistry
from .parsers.openspec import (
    OpenSpecDeltaParser,
    OpenSpecFileDiscovery,
    OpenSpecSpecParser,
    RawDocumentParser,
    is_delta_sheet,
    is_non_python_code,
    is_openspec_non_md,
    is_spec_sheet,
)
from .parsers.text_symbols import TextSymbolsParser

__all__ = ["RepositoryProfile", "known_profiles", "resolve_profile"]


@dataclass(frozen=True)
class RepositoryProfile:
    """Parser dispatch + file selection for one repository convention.

    ``sniff_markers`` are path prefixes whose presence in ``list_files()``
    output identifies the convention during ``auto`` resolution; the tuple is
    checked in registration order and the first match wins.
    """

    name: str
    sniff_markers: tuple[str, ...]
    registry: ParserRegistry
    discovery: FileDiscovery


def _build_specweaver() -> RepositoryProfile:
    """The project's own template convention (demo/railway); the default."""
    return RepositoryProfile(
        name="specweaver",
        sniff_markers=("specs/", "design/", "rules/"),
        registry=ParserRegistry(),
        discovery=FileDiscovery(),
    )


def _build_plain() -> RepositoryProfile:
    """Fallback for arbitrary repositories: Tier-2 mining for non-Python code."""
    return RepositoryProfile(
        name="plain",
        sniff_markers=(),
        registry=ParserRegistry(
            entries=[(is_non_python_code, TextSymbolsParser())]
        ),
        discovery=FileDiscovery(),
    )


def _build_openspec() -> RepositoryProfile:
    """OpenSpec convention (specs / pending-change deltas / archive)."""
    return RepositoryProfile(
        name="openspec",
        sniff_markers=("openspec/",),
        registry=ParserRegistry(
            entries=[
                (lambda path, _type: is_spec_sheet(path), OpenSpecSpecParser()),
                (lambda path, _type: is_delta_sheet(path), OpenSpecDeltaParser()),
                (is_openspec_non_md, RawDocumentParser()),
                (is_non_python_code, TextSymbolsParser()),
            ]
        ),
        discovery=OpenSpecFileDiscovery(),
    )


# Registration order doubles as sniff order: most specific convention first.
_BUILDERS: dict[str, Callable[[], RepositoryProfile]] = {
    "openspec": _build_openspec,
    "specweaver": _build_specweaver,
    "plain": _build_plain,
}


def known_profiles() -> list[str]:
    return sorted((*_BUILDERS, "auto"))


async def resolve_profile(
    workspace: WorkspacePort,
    requested: str = "",
    configured: str = "auto",
) -> RepositoryProfile:
    """Resolve the effective profile: request beats setting beats sniffing.

    ``auto`` sniffs the workspace listing against each profile's markers;
    anything unrecognized falls back to the default (specweaver) convention.
    """
    name = (requested or "").strip() or (configured or "").strip() or "auto"
    if name != "auto":
        builder = _BUILDERS.get(name)
        if builder is None:
            raise InvalidRequest(
                f"unknown repository profile {name!r}; known: "
                f"{', '.join(known_profiles())}"
            )
        return builder()
    paths = await workspace.list_files()
    for builder in _BUILDERS.values():
        profile = builder()
        if not profile.sniff_markers:
            continue
        for path in paths:
            normalized = path.replace("\\", "/").lower()
            if any(
                normalized.startswith(marker)
                for marker in profile.sniff_markers
            ):
                return profile
    return _build_specweaver()
