from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .enums import ArtifactType, LifecycleStatus, RelationKind, TaskPhase
from .values import Budget, Citation, Finding, SourceRef


class Artifact(BaseModel):
    id: str
    project_id: str
    type: ArtifactType
    module: str | None = None
    title: str
    content: str = ""
    version: str = "0.1.0"
    status: LifecycleStatus = LifecycleStatus.active
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    applies_to_ref: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    source: SourceRef | None = None
    checksum: str | None = None
    tags: list[str] = []
    based_on: list[str] = []
    embedding: list[float] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Relation(BaseModel):
    id: str | None = None
    project_id: str
    src: str
    dst: str
    kind: RelationKind
    confidence: float = 1.0
    evidence: str | None = None


class Task(BaseModel):
    id: str
    project_id: str
    title: str
    objective: str = ""
    phase: TaskPhase = TaskPhase.analyzing
    branch: str | None = None
    base_ref: str | None = None
    handoff_rev: str | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None


class FileChange(BaseModel):
    path: str
    change_type: str  # added / modified / deleted
    symbols: list[str] = []


class ChangeSet(BaseModel):
    id: str
    project_id: str = ""
    task_id: str
    files_changed: list[FileChange] = []
    base_checksum: str | None = None
    head_checksum: str | None = None
    test_run_id: str | None = None


class TestRun(BaseModel):
    __test__ = False

    id: str
    project_id: str = ""
    task_id: str
    command: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    report_ref: str | None = None
    commit_ref: str | None = None


class ContextBundle(BaseModel):
    task: Task
    goal_and_constraints: list[Artifact] = []
    design_and_implementation: list[Artifact] = []
    verification: list[Artifact] = []
    findings: list[Finding] = []
    citations: list[Citation] = []
    budget: Budget | None = None
    generated_at: datetime | None = None
