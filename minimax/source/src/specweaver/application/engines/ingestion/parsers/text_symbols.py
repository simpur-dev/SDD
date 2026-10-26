"""Tier-2 text symbol extraction for languages without an ast reader.

Regular-expression symbol mining for stacks the stdlib ``ast`` parser cannot
cover (TypeScript/JavaScript, Go, Rust, ...). Deliberately weaker than Tier 1:
names and imports only, no calls or scopes — edges mined from these documents
already carry the lower confidence and the "naming convention" evidence kind,
so downstream never mistakes them for precise analysis (v0.4 §2.2 keeps exact
symbol work on the agent's own tools).
"""

from __future__ import annotations

import os
import re

from .....domain.enums import ArtifactType
from .base import ParsedDocument, ParsedSymbol
from .markdown import extract_refs

_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+"
    r"([A-Za-z_$][\w$]*)",
    re.M,
)
_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface)\s+"
    r"([A-Za-z_$][\w$]*)",
    re.M,
)
_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?:async\s*)?\(",
    re.M,
)
_CASE_RE = re.compile(r"\b(?:it|test)\(\s*['\"`]([^'\"`]+)['\"`]")
_IMPORT_RE = re.compile(
    r"""(?:from\s+['"]([^'"]+)['"])|(?:require\(\s*['"]([^'"]+)['"]\s*\))"""
)
_TEST_FILE_RE = re.compile(r"\.(spec|test)\.[cm]?[jt]sx?$", re.IGNORECASE)
_LINE_NO_RE = re.compile(r"\n")


def _line_at(text: str, offset: int) -> int:
    return _LINE_NO_RE.sub("\n", text[:offset]).count("\n") + 1


def _import_package(target: str) -> str:
    """'./schedule' / '@/lib/search' / 'react' -> indexable module name."""
    trimmed = target.strip().strip("'\"")
    stem = trimmed.rsplit("/", 1)[-1]
    stem = stem.removesuffix(".js").removesuffix(".mjs").removesuffix(".cjs")
    return stem


def _test_target(stem: str) -> str:
    for marker in (".spec", ".test"):
        if stem.lower().endswith(marker):
            return stem[: -len(marker)]
    return stem


class TextSymbolsParser:
    """Regex-based symbols/imports for non-Python code and test files."""

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> list[ParsedDocument]:
        is_test = bool(_TEST_FILE_RE.search(path)) or (
            declared_type is ArtifactType.test
        )

        symbols: list[ParsedSymbol] = []
        seen: set[tuple[str, str]] = set()

        def add(name: str, kind: str, offset: int, raw: str) -> None:
            key = (name, kind)
            if key in seen:
                return
            seen.add(key)
            symbols.append(
                ParsedSymbol(
                    name=name,
                    kind="test_case" if is_test and kind == "function" else kind,
                    line=_line_at(text, offset),
                    signature=raw.strip()[:200],
                )
            )

        for match in _FUNCTION_RE.finditer(text):
            add(match.group(1), "function", match.start(1), match.group(0))
        for match in _CLASS_RE.finditer(text):
            add(match.group(1), "class", match.start(1), match.group(0))
        for match in _ARROW_RE.finditer(text):
            add(match.group(1), "function", match.start(1), match.group(0))
        if is_test:
            case_names = [
                name.strip() for name in _CASE_RE.findall(text)
            ]
            for name in case_names:
                add(name, "test_case", text.index(name), f"it('{name}')")

        imports: list[str] = []
        for match in _IMPORT_RE.finditer(text):
            target = match.group(1) or match.group(2) or ""
            package = _import_package(target)
            if package and package not in imports:
                imports.append(package)

        stem = os.path.splitext(os.path.basename(path))[0]
        front_matter: dict = {}
        if is_test:
            front_matter["test_target_module"] = _test_target(stem)

        return [
            ParsedDocument(
                path=path,
                type=ArtifactType.test if is_test else ArtifactType.code,
                title=stem,
                symbols=symbols,
                behavior_points=(
                    [s.name for s in symbols if s.kind == "test_case"]
                    if is_test
                    else []
                ),
                references=extract_refs(text),
                imports=imports,
                front_matter=front_matter,
                checksum=checksum,
                raw_text=text,
            )
        ]
