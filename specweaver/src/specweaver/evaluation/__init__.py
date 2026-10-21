"""Evaluation contracts: declarative inputs and outputs for reproducible runs.

``taskpack.py`` — the TaskPack manifest (input side, this module).
``artifact.py`` — the EvalRun structured result (output side, M7 planned).

Import direction is ``evaluation -> application + shared`` (docs/03 §2.1):
this package drives application use cases from scripts, it registers no MCP
tools and adds no CLI commands — the only entry points live in ``scripts/``.
"""

from .taskpack import (
    SCHEMA_VERSION,
    AcceptanceSpec,
    AgentSpec,
    BudgetSpec,
    ExecutionPlan,
    RepoSpec,
    SnapshotSpec,
    TaskPack,
    TaskSpec,
    load_dir,
    load_pack,
    materialize,
)

__all__ = [
    "SCHEMA_VERSION",
    "TaskPack",
    "AgentSpec",
    "RepoSpec",
    "TaskSpec",
    "SnapshotSpec",
    "BudgetSpec",
    "AcceptanceSpec",
    "ExecutionPlan",
    "load_pack",
    "load_dir",
    "materialize",
]
