from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .....domain.enums import ArtifactType


class ParsedSymbol(BaseModel):
    """A named code/behavior unit extracted by a parser."""

    name: str
    kind: str  # function / class / method / test_case
    line: int
    end_line: int | None = None
    signature: str | None = None
    docstring: str | None = None
    refs: list[str] = []


class ParsedDocument(BaseModel):
    """Normalized, type-agnostic output of a parser."""

    path: str
    type: ArtifactType
    title: str
    summary: str = ""
    symbols: list[ParsedSymbol] = []
    behavior_points: list[str] = []
    constraints: list[str] = []
    references: list[str] = []
    imports: list[str] = []
    front_matter: dict = {}
    checksum: str | None = None
    raw_text: str = ""


class Parser(Protocol):
    """Synchronous, CPU-only parser: file text -> ParsedDocument."""

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> ParsedDocument: ...
