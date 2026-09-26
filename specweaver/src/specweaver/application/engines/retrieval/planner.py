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


def planner_prompt(task: str, known_modules: list[str] | None) -> str:
    prompt = f"{PLANNER_INSTRUCTION}\n\nTask: {task}"
    if known_modules:
        prompt += (
            "\n\nKnown project modules (ONLY choose module names from this "
            f"list, or leave modules empty): {', '.join(known_modules)}"
        )
    return prompt


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

    def __init__(self, llm=None, telemetry=None) -> None:
        self._llm = llm
        self._telemetry = telemetry

    async def plan(
        self, task: str, known_modules: list[str] | None = None
    ) -> RetrievalPlan:
        structured: object = None
        llm_error = ""
        if self._llm is not None:
            try:
                result = await self._llm.complete(
                    planner_prompt(task, known_modules),
                    schema={"type": "object"},
                )
                structured = result.structured
                if self._telemetry is not None:
                    self._telemetry.record_llm_usage(
                        result.usage.prompt_tokens,
                        result.usage.completion_tokens,
                    )
            except Exception as exc:  # noqa: BLE001 - network/model failure -> fallback
                structured = None
                # degrade loudly: the reason must be visible downstream
                llm_error = str(exc)[:120]
        if isinstance(structured, dict):
            modules = _coerce_str_list(structured.get("modules"))
            if known_modules:
                # hallucinated module names would filter the catalog to
                # empty; keep only modules that actually exist
                allowed = set(known_modules)
                modules = [m for m in modules if m in allowed]
            return RetrievalPlan(
                objective=str(structured.get("objective") or task),
                keywords=_coerce_str_list(structured.get("keywords")),
                modules=modules,
                types=_coerce_types(structured.get("types")),
                rationale="llm planning",
            )
        rationale = "rule-based planning"
        if llm_error:
            rationale = f"rule-based planning (llm unavailable: {llm_error})"
        return RetrievalPlan(
            objective=task, keywords=rule_keywords(task), rationale=rationale
        )
