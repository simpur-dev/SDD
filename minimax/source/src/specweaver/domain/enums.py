from enum import StrEnum


class ArtifactType(StrEnum):
    requirement = "requirement"
    design = "design"
    code = "code"
    test = "test"
    rule = "rule"


class LifecycleStatus(StrEnum):
    draft = "draft"
    active = "active"
    superseded = "superseded"
    deprecated = "deprecated"


class RelationKind(StrEnum):
    realizes = "realizes"
    refines = "refines"
    covers = "covers"
    constrains = "constrains"
    calls = "calls"
    tests = "tests"
    depends_on = "depends_on"
    supersedes = "supersedes"


class TaskPhase(StrEnum):
    analyzing = "analyzing"
    in_progress = "in_progress"
    verifying = "verifying"
    handoff = "handoff"
    done = "done"
    blocked = "blocked"


class FindingKind(StrEnum):
    conflict = "conflict"
    gap = "gap"
    suspect = "suspect"
    unverified = "unverified"


class Severity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"
