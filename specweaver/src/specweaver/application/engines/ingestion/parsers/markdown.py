from __future__ import annotations

import os
import re

from .....domain.enums import ArtifactType
from ..taxonomy import normalize_type
from .base import ParsedDocument

_ID_RE = re.compile(r"\b(REQ|TST|DES|ADR|RULE)[-_ ]?(\d{1,5})\b")
_TAG_RE = re.compile(
    r"@(?:implements|covers|realizes|tests|refines)\s+"
    r"([A-Z]{2,5})[-_ ]?(\d{1,5})\b"
)
_PREFIX = {"REQ": "REQ", "TST": "TST", "DES": "DES", "ADR": "DES",
           "RULE": "RULE"}

_BEHAVIOR_HEADINGS = (
    "需求", "行为", "功能", "验收", "场景", "acceptance", "behavior",
    "requirement", "functional", "user story", "决策", "decision",
)
_CONSTRAINT_HEADINGS = (
    "约束", "限制", "非功能", "规则", "constraint", "rule", "禁止",
)
_CONSTRAINT_WORDS = re.compile(r"禁止|不得|严禁|不能|must not|shall not")
_BEHAVIOR_WORDS = re.compile(r"应|必须|须|shall|must|should")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$")


def extract_refs(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    def add(prefix: str, number: str) -> None:
        normalized = f"{_PREFIX[prefix]}-{int(number)}"
        if normalized not in seen:
            seen.add(normalized)
            refs.append(normalized)

    for prefix, number in _TAG_RE.findall(text):
        add(prefix, number)
    for prefix, number in _ID_RE.findall(text):
        add(prefix, number)
    return refs


def split_front_matter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    closing = next(
        (i for i in range(1, len(lines)) if lines[i].strip() == "---"), None
    )
    if closing is None:
        return {}, text
    front_matter: dict = {}
    for line in lines[1:closing]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        front_matter[key.strip().lower()] = value
    return front_matter, "\n".join(lines[closing + 1:])


class MarkdownParser:
    """Parses requirement/design/rule markdown; effective type from front matter."""

    def parse(
        self,
        path: str,
        text: str,
        checksum: str | None,
        declared_type: ArtifactType,
    ) -> ParsedDocument:
        front_matter, body = split_front_matter(text)
        effective_type = normalize_type(front_matter.get("type")) or declared_type

        title = front_matter.get("title") or self._first_heading(body, 1)
        if not title:
            title = os.path.splitext(os.path.basename(path))[0]

        behavior: list[str] = []
        constraints: list[str] = []
        summary_parts: list[str] = []
        current = ""
        for line in body.splitlines():
            heading = _HEADING_RE.match(line)
            if heading:
                current = heading.group(2).strip().lower()
                continue
            item = _LIST_RE.match(line)
            if item:
                self._classify_item(
                    item.group(1).strip(), current, behavior, constraints
                )
            elif line.strip() and not line.lstrip().startswith("#"):
                if len(summary_parts) < 3:
                    summary_parts.append(line.strip())

        return ParsedDocument(
            path=path,
            type=effective_type,
            title=title,
            summary=" ".join(summary_parts)[:400],
            behavior_points=self._dedupe(behavior),
            constraints=self._dedupe(constraints),
            references=extract_refs(text),
            front_matter=front_matter,
            checksum=checksum,
            raw_text=text,
        )

    @staticmethod
    def _first_heading(body: str, level: int) -> str | None:
        for line in body.splitlines():
            match = _HEADING_RE.match(line)
            if match and len(match.group(1)) == level:
                return match.group(2).strip()
        return None

    @staticmethod
    def _classify_item(item, heading, behavior, constraints) -> None:
        if _CONSTRAINT_WORDS.search(item):
            constraints.append(item)
        elif any(word in heading for word in _CONSTRAINT_HEADINGS):
            constraints.append(item)
        elif any(word in heading for word in _BEHAVIOR_HEADINGS):
            behavior.append(item)
        elif _BEHAVIOR_WORDS.search(item):
            behavior.append(item)

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        out: list[str] = []
        for item in items:
            if item not in out:
                out.append(item)
        return out
