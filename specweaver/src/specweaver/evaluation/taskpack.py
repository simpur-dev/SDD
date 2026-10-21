"""TaskPack schema v1: one declarative manifest per reproducible evaluation run.

A TaskPack pins every input the brief v0.4 asks evaluations to fix — the
repository at a pinned commit, the agent's name/version/model/tool
allowlist, the task, the initial-snapshot kind and the run budget — so two
runs of the same pack are comparable and a failed tier never blocks another
(§2.3 "各层独立可启动的初始快照").

The snapshot-isolation protocol rests on mechanisms that already exist:
independent checkouts per run (repo isolation), the seekdb record key
``{project}:{id}`` (catalog isolation) and the deterministic PowerContext
scope title ``sw:{project}`` (memory isolation). :func:`materialize` makes
those derivations explicit and testable instead of leaving them as harness
conventions.

This module is pure: no IO beyond what the caller hands in, no git, no
backend. Commit existence and other environment checks belong to the
consumer script (``scripts/taskpack_check.py``, later ``run_eval.py``).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..application.engines.ingestion.profiles import known_profiles
from ..shared.errors import InvalidRequest

SCHEMA_VERSION = 1

# A manifest must reject unknown fields: a typo like "comit" would otherwise
# silently fall back to defaults and produce an run nobody can reproduce.
_MANIFEST_STRICTNESS = ConfigDict(extra="forbid")

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class AgentSpec(BaseModel):
    """The coding agent under test, fixed as the brief requires."""

    model_config = _MANIFEST_STRICTNESS

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tool_allowlist: list[str] = []  # empty = unrestricted (all sw_ tools)

    @field_validator("tool_allowlist")
    @classmethod
    def _tools_are_namespaced(cls, value: list[str]) -> list[str]:
        for tool in value:
            if not tool.startswith("sw_"):
                raise ValueError(
                    f"tool {tool!r} must be a sw_-prefixed SpecWeaver tool"
                )
        return value


class RepoSpec(BaseModel):
    """Repository under test, pinned to an exact commit."""

    model_config = _MANIFEST_STRICTNESS

    origin: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    subdir: str = ""  # workspace root inside the checkout ("" = checkout root)
    profile: str = "auto"  # repository profile for ingestion (docs/01 §5.5)

    @field_validator("profile")
    @classmethod
    def _profile_exists(cls, value: str) -> str:
        if value not in known_profiles():
            raise ValueError(
                f"unknown repository profile {value!r}; known: "
                f"{', '.join(known_profiles())}"
            )
        return value


class TaskSpec(BaseModel):
    model_config = _MANIFEST_STRICTNESS

    goal: str = Field(min_length=1)
    givens: list[str] = []  # spec entries / constraints handed to the agent
    # Precise interface contract appended to the agent prompt (hidden
    # acceptance tests will import exactly these); empty = goal only.
    contract: str = ""


class SnapshotSpec(BaseModel):
    """v1 supports fresh snapshots only; seed references come with v2."""

    model_config = _MANIFEST_STRICTNESS

    seekdb: Literal["fresh"] = "fresh"
    powercontext_scope: Literal["fresh"] = "fresh"


class BudgetSpec(BaseModel):
    """Soft ceilings: the harness reports actuals vs declared, never silently
    truncates (docs/01 §10.6)."""

    model_config = _MANIFEST_STRICTNESS

    max_tokens: int | None = Field(default=None, ge=1)
    max_backend_calls: int | None = Field(default=None, ge=1)
    time_limit_s: int | None = Field(default=None, ge=1)


class AcceptanceSpec(BaseModel):
    model_config = _MANIFEST_STRICTNESS

    test_commands: list[str] = Field(min_length=1)
    forbidden_regressions: list[str] = []  # artifact ids that must keep passing
    # Hidden acceptance test file, path relative to the taskpack manifest's
    # own directory; injected into the workspace only after the agent's diff
    # is captured, so it can grade but not leak into the prompt.
    hidden_suite: str = ""


class TaskPack(BaseModel):
    model_config = _MANIFEST_STRICTNESS

    schema_version: Literal[1] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,62}$")
    tier: Literal["basic", "advanced", "challenge"]
    title: str = ""
    repo: RepoSpec
    agent: AgentSpec
    task: TaskSpec
    snapshot: SnapshotSpec = SnapshotSpec()
    budget: BudgetSpec = BudgetSpec()
    acceptance: AcceptanceSpec


@dataclass(frozen=True)
class ExecutionPlan:
    """A TaskPack materialized for one run: the isolation derivations."""

    pack_id: str
    tier: str
    run_id: str
    project_id: str  # seekdb catalog isolation: record key {project}:{id}
    scope_title: str  # PowerContext memory isolation: title `sw:{project}`
    workspace_dir: str  # checkout/copy target (repo isolation)
    workspace_subdir: str
    profile: str

    def summary(self) -> dict[str, str]:
        return asdict(self)


def load_pack(path: Path | str) -> TaskPack:
    """Load and validate one manifest; errors name the file and the field."""
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidRequest(f"{target}: unreadable taskpack ({exc})") from exc
    try:
        return TaskPack.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise InvalidRequest(f"{target}: invalid taskpack — {details}") from exc


def load_dir(directory: Path | str) -> list[TaskPack]:
    """Load every ``*.json`` manifest in a directory, sorted by file name."""
    folder = Path(directory)
    paths = sorted(folder.glob("*.json"))
    if not paths:
        raise InvalidRequest(f"{folder}: no taskpack (*.json) found")
    return [load_pack(path) for path in paths]


def materialize(
    pack: TaskPack, run_id: str, workroot: Path | str
) -> ExecutionPlan:
    """Derive the per-run isolated identities for a pack.

    Distinct ``run_id`` values yield distinct project ids, scope titles and
    workspace directories — that is the whole independence guarantee; idempotent
    ingestion then makes re-running the same run converge to the same state.
    """
    run = (run_id or "").strip()
    if not _RUN_ID_RE.fullmatch(run):
        raise InvalidRequest(
            f"run_id {run_id!r} must match {_RUN_ID_RE.pattern}"
        )
    project_id = f"{pack.id}-{run}"
    return ExecutionPlan(
        pack_id=pack.id,
        tier=pack.tier,
        run_id=run,
        project_id=project_id,
        scope_title=f"sw:{project_id}",
        workspace_dir=str(Path(workroot) / project_id),
        workspace_subdir=pack.repo.subdir,
        profile=pack.repo.profile,
    )
