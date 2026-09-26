from __future__ import annotations

import re

from pydantic import BaseModel

from ....domain.enums import ArtifactType

_STOPWORDS = frozenset(
    {"the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "is",
     "are", "be", "with", "this", "that"}
)
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]+")

PLANNER_INSTRUCTION = (
    "You are a retrieval planner for spec-driven development. From the "
    "developer task, return JSON with keys: objective (string), keywords "
    "(array of concise search terms), modules (array of likely module names, "
    "may be empty), types (array chosen from requirement/design/code/test/"
    "rule, may be empty)."
)


class RetrievalPlan(BaseModel):
    objective: str
    keywords: list[str] = []
    modules: list[str] = []
    types: list[ArtifactType] = []
    rationale: str = "rule-based planning"


def rule_keywords(task: str) -> list[str]:
    keywords: list[str] = []
    for token in _TOKEN_RE.findall(task):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]+", token):
            lowered = token.lower()
            if lowered not in _STOPWORDS and len(lowered) >= 2:
                keywords.append(lowered)
        else:
            keywords.append(token)  # CJK run
    return keywords[:16]


def _coerce_types(values: object) -> list[ArtifactType]:
    if not isinstance(values, list):
        return []
    types: list[ArtifactType] = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            types.append(ArtifactType(value))
        except ValueError:
            continue
    return types


def _coerce_str_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


class QueryPlanner:
    """Plans retrieval: LLM intent extraction with a deterministic fallback."""

    def __init__(self, llm=None) -> None:
        self._llm = llm

    async def plan(self, task: str) -> RetrievalPlan:
        structured: object = None
        if self._llm is not None:
            try:
                result = await self._llm.complete(
                    f"{PLANNER_INSTRUCTION}\n\nTask: {task}",
                    schema={"type": "object"},
                )
                structured = result.structured
            except Exception:  # noqa: BLE001 - network/model failure -> fallback
                structured = None
        if isinstance(structured, dict):
            return RetrievalPlan(
                objective=str(structured.get("objective") or task),
                keywords=_coerce_str_list(structured.get("keywords")),
                modules=_coerce_str_list(structured.get("modules")),
                types=_coerce_types(structured.get("types")),
                rationale="llm planning",
            )
        return RetrievalPlan(objective=task, keywords=rule_keywords(task))
