from __future__ import annotations

import os

from .....domain.enums import ArtifactType
from .base import ParsedDocument, ParsedSymbol, Parser
from .markdown import MarkdownParser
from .python_code import PythonCodeParser
from .python_test import PythonTestParser

_MD_EXTS = frozenset({".md", ".markdown"})

__all__ = [
    "ParsedDocument",
    "ParsedSymbol",
    "Parser",
    "ParserRegistry",
    "MarkdownParser",
    "PythonCodeParser",
    "PythonTestParser",
]


class ParserRegistry:
    """Selects a parser by file extension and declared artifact type."""

    def __init__(self) -> None:
        self._markdown = MarkdownParser()
        self._code = PythonCodeParser()
        self._test = PythonTestParser()

    def for_file(self, path: str, declared_type: ArtifactType) -> Parser:
        ext = os.path.splitext(path)[1].lower()
        if ext in _MD_EXTS:
            return self._markdown
        if declared_type == ArtifactType.test:
            return self._test
        return self._code
