"""Evaluation contracts: declarative inputs and outputs for reproducible runs.

``taskpack.py`` — the TaskPack manifest (input side).
``artifact.py`` — the EvalRun structured result (output side) plus the
collectors that aggregate it from the two existing evidence layouts.

Import direction is ``evaluation -> application + shared`` (docs/03 §2.1):
this package drives application use cases from scripts, it registers no MCP
tools and adds no CLI commands — the only entry points live in ``scripts/``.
"""

from .artifact import (
    EVALRUN_SCHEMA_VERSION,
    AgentRef,
    BudgetBlock,
    BundleRef,
    CitationRef,
    CodeDiff,
    EvalMeta,
    EvalRun,
    MemoryOp,
    OutcomeBlock,
    TestEvidence,
    UsageBlock,
    build_evalrun,
    collect_demo,
    collect_off_on,
    detect_layout,
    load_evalrun,
)
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
    "EVALRUN_SCHEMA_VERSION",
    "EvalRun",
    "EvalMeta",
    "AgentRef",
    "CitationRef",
    "BundleRef",
    "CodeDiff",
    "TestEvidence",
    "MemoryOp",
    "UsageBlock",
    "BudgetBlock",
    "OutcomeBlock",
    "build_evalrun",
    "load_evalrun",
    "collect_demo",
    "collect_off_on",
    "detect_layout",
]
