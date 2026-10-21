"""EvalRun schema v1: the machine-readable result of one evaluation run.

EvalRun is the output-side counterpart of a TaskPack (``taskpack.py``): the
pack declares how an evaluation is run, the EvalRun records what came out of
it — context bundles with citations, the code diff, test evidence, memory
operations, usage against the declared budget, and the acceptance outcome —
in one schema-checked JSON whose ``*_ref`` fields and ``sources`` list always
point back at the concrete evidence files (docs/01 §11.2).

Two evidence layouts can be aggregated today:

- ``railway-demo``: ``scripts/run_demo.py`` output (step dumps ``0N-*.json``,
  ``usage.csv``, ``powercontext-actions.jsonl``, ``changes-*.diff``);
- ``off-on``: ``scripts/run_off_on.py`` output (``summary.json`` record array
  plus per-run subdirs with ``transcript.jsonl`` / ``agent.diff`` / ``judge.txt``).

The future ``run_eval.py`` harness will feed :func:`build_evalrun` directly
from in-memory reports and telemetry spans — the builder itself is pure and
layout-agnostic. Budget ceilings are soft: declared-vs-actual is reported,
never silently truncated.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..shared.errors import InvalidRequest
from .taskpack import TaskPack

EVALRUN_SCHEMA_VERSION = 1

# Same strictness as TaskPack: an EvalRun is a contract, a typo'd producer
# field must fail loudly instead of drifting into the archive.
_STRICT = ConfigDict(extra="forbid")


class AgentRef(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1)
    version: str = ""
    model: str = ""


class EvalMeta(BaseModel):
    model_config = _STRICT

    source: Literal["railway-demo", "off-on", "run_eval"]
    arm: Literal["", "off", "on"] = ""
    run_index: int | None = None
    agent: AgentRef
    sw_version: str = ""
    started_at: str = ""
    taskpack_id: str = ""
    tier: str = ""


class CitationRef(BaseModel):
    model_config = _STRICT

    artifact_id: str
    version: str = ""
    source_uri: str = ""
    locator: str = ""
    updated_at: str = ""


class BundleRef(BaseModel):
    model_config = _STRICT

    task: str = ""
    bundle_ref: str
    citations: list[CitationRef] = []
    findings: int = 0
    bundle_bytes: int = 0
    excluded: int = 0


class CodeDiff(BaseModel):
    model_config = _STRICT

    diff_refs: list[str] = []
    files_changed: list[str] = []


class TestEvidence(BaseModel):
    model_config = _STRICT

    command: str
    exit_code: int | None = None
    passed: int | None = None
    failed: int | None = None
    total: int | None = None
    summary: str = ""
    report_ref: str = ""


class MemoryOp(BaseModel):
    model_config = _STRICT

    action: str
    ref: str = ""
    detail: str = ""


class UsageBlock(BaseModel):
    model_config = _STRICT

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    backend_calls: int = 0
    duration_ms: float = 0.0
    spans: int = 0
    agent_usage_raw: dict[str, Any] = {}  # provider-specific fields, verbatim


class BudgetBlock(BaseModel):
    model_config = _STRICT

    declared: dict[str, float] = {}
    actual: dict[str, float] = {}
    over: list[str] = []  # declared keys whose actual exceeded the ceiling


class OutcomeBlock(BaseModel):
    model_config = _STRICT

    success: bool | None = None
    source: str = ""  # which recorded field decided success, e.g. summary.success
    notes: list[str] = []


class EvalRun(BaseModel):
    model_config = _STRICT

    schema_version: Literal[1] = EVALRUN_SCHEMA_VERSION
    meta: EvalMeta
    context_bundles: list[BundleRef] = []
    code_diff: CodeDiff = CodeDiff()
    test_evidence: list[TestEvidence] = []
    memory_ops: list[MemoryOp] = []
    usage: UsageBlock = UsageBlock()
    budget: BudgetBlock = BudgetBlock()
    outcome: OutcomeBlock = OutcomeBlock()
    sources: list[str] = []


def load_evalrun(path: Path | str) -> EvalRun:
    """Load and validate one EvalRun; errors name the file."""
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidRequest(f"{target}: unreadable evalrun ({exc})") from exc
    try:
        return EvalRun.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise InvalidRequest(f"{target}: invalid evalrun — {details}") from exc


def build_evalrun(
    meta: EvalMeta,
    *,
    bundles: list[BundleRef] | None = None,
    diff: CodeDiff | None = None,
    tests: list[TestEvidence] | None = None,
    memory_ops: list[MemoryOp] | None = None,
    usage: UsageBlock | None = None,
    outcome: OutcomeBlock | None = None,
    sources: list[str] | None = None,
    taskpack: TaskPack | None = None,
) -> EvalRun:
    """Single aggregation point, pure: soft-budget comparison lives here.

    Only keys actually declared in the TaskPack participate in the over[]
    check; with no pack attached the budget block stays empty instead of
    inventing defaults.
    """
    usage = usage or UsageBlock()
    declared: dict[str, float] = {}
    actual: dict[str, float] = {}
    over: list[str] = []
    if taskpack is not None:
        candidates = {
            "max_tokens": (
                taskpack.budget.max_tokens,
                float(usage.prompt_tokens + usage.completion_tokens),
            ),
            "max_backend_calls": (
                taskpack.budget.max_backend_calls,
                float(usage.backend_calls),
            ),
            "time_limit_s": (
                taskpack.budget.time_limit_s,
                usage.duration_ms / 1000,
            ),
        }
        for key, (limit, measured) in candidates.items():
            if limit is None:
                continue
            declared[key] = float(limit)
            actual[key] = measured
            if measured > limit:
                over.append(key)
    return EvalRun(
        meta=meta,
        context_bundles=bundles or [],
        code_diff=diff or CodeDiff(),
        test_evidence=tests or [],
        memory_ops=memory_ops or [],
        usage=usage,
        budget=BudgetBlock(declared=declared, actual=actual, over=over),
        outcome=outcome or OutcomeBlock(),
        sources=sources or [],
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidRequest(f"{path}: unreadable evidence file ({exc})") from exc


def _citation_ref(raw: dict) -> CitationRef:
    source = raw.get("source") or {}
    return CitationRef(
        artifact_id=str(raw.get("artifact_id", "")),
        version=str(raw.get("version") or ""),
        source_uri=str(source.get("uri") or ""),
        locator=str(source.get("locator") or ""),
        updated_at=str(raw.get("updated_at") or ""),
    )


def detect_layout(directory: Path | str) -> Literal["off-on", "railway-demo"]:
    """Recognize the evidence layout or fail naming the directory."""
    root = Path(directory)
    if (root / "summary.json").is_file():
        return "off-on"
    if (root / "01-ingest.json").is_file():
        return "railway-demo"
    raise InvalidRequest(
        f"{root}: unrecognized evidence layout (need summary.json or "
        "01-ingest.json)"
    )


def collect_demo(
    directory: Path | str,
    *,
    agent: AgentRef,
    sw_version: str = "",
    taskpack: TaskPack | None = None,
) -> EvalRun:
    """Aggregate a run_demo-style directory (step dumps + usage.csv)."""
    root = Path(directory)
    if not (root / "01-ingest.json").is_file():
        raise InvalidRequest(
            f"{root}: not a railway-demo evidence directory "
            "(missing 01-ingest.json)"
        )
    sources: list[str] = []
    usage = UsageBlock()

    csv_path = root / "usage.csv"
    if csv_path.is_file():
        sources.append("usage.csv")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                usage.spans += 1
                usage.llm_calls += int(row.get("llm_calls") or 0)
                usage.prompt_tokens += int(row.get("prompt_tokens") or 0)
                usage.completion_tokens += int(
                    row.get("completion_tokens") or 0
                )
                usage.backend_calls += int(row.get("backend_calls") or 0)
                usage.duration_ms += float(row.get("duration_ms") or 0)

    bundles: list[BundleRef] = []
    for name in ("02-context.json", "07-context-final.json"):
        path = root / name
        if not path.is_file():
            continue
        sources.append(name)
        data = _read_json(path)
        bundle = data.get("bundle") or {}
        task = bundle.get("task")
        budget = bundle.get("budget") or {}
        bundles.append(
            BundleRef(
                task=str(task.get("title", "")) if isinstance(task, dict) else "",
                bundle_ref=name.replace(".json", ".md"),
                citations=[
                    _citation_ref(c) for c in bundle.get("citations", [])
                ],
                findings=len(bundle.get("findings", [])),
                bundle_bytes=int(budget.get("used_bytes") or 0),
                excluded=len(data.get("excluded", [])),
            )
        )

    tests: list[TestEvidence] = []
    files_changed: list[str] = []
    success: bool | None = None
    for name in ("03-complete-adjust.json", "06-complete-audit.json"):
        path = root / name
        if not path.is_file():
            continue
        sources.append(name)
        data = _read_json(path)
        if success is None and "success" in data:
            success = bool(data["success"])
        tests.append(
            TestEvidence(
                command="pytest (via complete_task)",
                total=data.get("test_total"),
                passed=data.get("test_passed"),
                failed=data.get("test_failed"),
                summary=f"success={data.get('success')}",
                report_ref=name,
            )
        )
        for changed in data.get("files_changed", []):
            if isinstance(changed, str):
                files_changed.append(changed)
    diff_refs = [
        name
        for name in ("changes-1.diff", "changes-2.diff")
        if (root / name).is_file()
    ]
    sources.extend(diff_refs)

    memory_ops: list[MemoryOp] = []
    handoff_path = root / "04-handoff.json"
    if handoff_path.is_file():
        sources.append("04-handoff.json")
        data = _read_json(handoff_path)
        memory_ops.append(
            MemoryOp(action="handoff", ref=str(data.get("handoff_rev", "")))
        )
    resume_path = root / "05-resume.json"
    if resume_path.is_file():
        sources.append("05-resume.json")
        data = _read_json(resume_path)
        mismatches = data.get("mismatches", [])
        memory_ops.append(
            MemoryOp(
                action="resume",
                detail=(
                    f"handoff_resumed={data.get('handoff_resumed')}, "
                    f"mismatches={len(mismatches)}"
                ),
            )
        )
    actions_path = root / "powercontext-actions.jsonl"
    if actions_path.is_file():
        sources.append("powercontext-actions.jsonl")
        for line in actions_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            memory_ops.append(
                MemoryOp(
                    action=str(record.get("op", "")),
                    ref=str(
                        record.get("entry_id")
                        or record.get("id")
                        or record.get("scope_id")
                        or ""
                    ),
                )
            )

    notes: list[str] = []
    ingest = _read_json(root / "01-ingest.json")
    sources.append("01-ingest.json")
    if ingest.get("duplicate_ids"):
        notes.append(f"duplicate_ids={ingest['duplicate_ids']}")
    if ingest.get("deprecated"):
        notes.append(f"deprecated={ingest['deprecated']}")

    return build_evalrun(
        EvalMeta(
            source="railway-demo",
            agent=agent,
            sw_version=sw_version,
            taskpack_id=taskpack.id if taskpack else "",
            tier=taskpack.tier if taskpack else "",
        ),
        bundles=bundles,
        diff=CodeDiff(diff_refs=diff_refs, files_changed=files_changed),
        tests=tests,
        memory_ops=memory_ops,
        usage=usage,
        outcome=OutcomeBlock(
            success=success, source="complete_task.success", notes=notes
        ),
        sources=sources,
        taskpack=taskpack,
    )


def collect_off_on(
    directory: Path | str,
    *,
    agent: AgentRef,
    sw_version: str = "",
    taskpack: TaskPack | None = None,
) -> list[EvalRun]:
    """Aggregate a run_off_on-style directory into one EvalRun per record."""
    root = Path(directory)
    summary = _read_json(root / "summary.json")
    if not isinstance(summary, list):
        raise InvalidRequest(
            f"{root}/summary.json: expected a run-record array"
        )

    runs: list[EvalRun] = []
    for record in summary:
        arm = str(record.get("arm", ""))
        index = record.get("run")
        run_dir = f"{arm}-{index}"
        sub = root / run_dir

        usage_raw = dict(record.get("usage") or {})
        usage = UsageBlock(
            prompt_tokens=int(usage_raw.get("input_tokens") or 0),
            completion_tokens=int(usage_raw.get("output_tokens") or 0),
            duration_ms=float(record.get("duration_ms") or 0),
            agent_usage_raw=usage_raw,
        )

        diff_refs = [
            f"{run_dir}/{name}"
            for name in ("agent.diff",)
            if (sub / name).is_file()
        ]
        tests = [
            TestEvidence(
                command="judge pytest",
                exit_code=record.get("pytest_rc"),
                summary=str(record.get("summary", "")),
                report_ref=f"{run_dir}/judge.txt",
            )
        ]
        sw_calls = list(record.get("sw_calls") or [])
        notes = [f"sw_calls={sw_calls}"] if sw_calls else []
        if record.get("error"):
            notes.append(f"error={record['error']}")
        notes.append(f"memory ops: see {run_dir}/transcript.jsonl")
        outcome = OutcomeBlock(
            success=record.get("success"),
            source="summary.success",
            notes=notes,
        )

        runs.append(
            build_evalrun(
                EvalMeta(
                    source="off-on",
                    arm=arm if arm in ("off", "on") else "",
                    run_index=index if isinstance(index, int) else None,
                    agent=agent,
                    sw_version=sw_version,
                    taskpack_id=taskpack.id if taskpack else "",
                    tier=taskpack.tier if taskpack else "",
                ),
                diff=CodeDiff(diff_refs=diff_refs),
                tests=tests,
                usage=usage,
                outcome=outcome,
                sources=[
                    "summary.json",
                    f"{run_dir}/transcript.jsonl",
                    f"{run_dir}/agent.diff",
                    f"{run_dir}/judge.txt",
                ],
                taskpack=taskpack,
            )
        )
    return runs
