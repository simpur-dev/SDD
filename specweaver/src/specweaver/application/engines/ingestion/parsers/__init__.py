from __future__ import annotations

import os
from collections.abc import Callable

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
    "ParserMatcher",
    "ParserRegistry",
    "MarkdownParser",
    "PythonCodeParser",
    "PythonTestParser",
]

ParserMatcher = Callable[[str, ArtifactType], bool]


class ParserRegistry:
    """Selects a parser by file extension and declared artifact type.

    ``entries`` are (predicate, parser) pairs evaluated in order before the
    default extension/type rules; profiles use them to route convention-
    specific files (e.g. OpenSpec specs) to dedicated parsers while keeping
    the fallback behavior identical to the default registry.
    """

    def __init__(
        self, entries: list[tuple[ParserMatcher, Parser]] | None = None
    ) -> None:
        self._entries = list(entries or [])
        self._markdown = MarkdownParser()
        self._code = PythonCodeParser()
        self._test = PythonTestParser()

    def for_file(self, path: str, declared_type: ArtifactType) -> Parser:
        for matcher, parser in self._entries:
            if matcher(path, declared_type):
                return parser
        ext = os.path.splitext(path)[1].lower()
        if ext in _MD_EXTS:
            return self._markdown
        if declared_type == ArtifactType.test:
            return self._test
        return self._code
