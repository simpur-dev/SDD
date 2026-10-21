"""Run-eval harness building blocks: what WOULD run, decided here, tested here.

``scripts/run_eval.py`` is the only entry point (docs/03 §16); every decision
it executes — clone/checkout plan, MCP server config, agent invocation and
prompt, transcript parsing, judge sequencing — lives in this module so it is
unit-testable without launching an agent. The run_off_on lesson learned: the
same logic lived inline in the script, untested and untestable.

Snapshot semantics (docs/01 §10.6): isolation comes from the per-run
project_id / scope / workspace of the ExecutionPlan — the shared backend is
never wiped; seekdb record keys ``{project}:{id}`` make cross-run bleed
physically impossible.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..shared.errors import InvalidRequest
from .taskpack import ExecutionPlan, TaskPack

SPECWEAVER_ROOT = Path(__file__).resolve().parents[3]
USAGE_OUT_ENV = "SPECWEAVER_USAGE_OUT"

ON_HINT = """

This workspace provides SpecWeaver MCP tools (mcp__specweaver__sw_*).
Recommended flow: sw_ingest_project (project id above), then sw_get_context \
(project id + this task) BEFORE editing; honor the constraints and findings \
it reports (rules, conflicts, gaps, stale specs). After tests are green, \
call sw_complete_task with base_ref = the git HEAD captured BEFORE your \
edits and test_command "python -m pytest -q"."""

ON_HINT_FULL = ON_HINT + """

This run additionally exercises the whole context lifecycle, so the
reviewer can see the loop closed by tooling instead of by memory:
1. sw_ping and sw_doctor first;
2. sw_get_context before editing, and honor the findings it reports;
3. sw_record_decision for the design decision you make (revise it with
   replaces_entry_id if you change your mind);
4. once tests are green: sw_handoff, then sw_resume_task with the
   returned handoff_rev, plus sw_report_progress with update_handoff=true;
5. sw_verify, and sw_explain_source on one artifact you relied on.
"""

HINTS: dict[str, str] = {"flow": ON_HINT, "full": ON_HINT_FULL}

# sw_ tools whose calls are memory/loop operations worth listing as MemoryOp
# evidence; anything else stays in the sw_calls note.
MEMORY_TOOLS = frozenset(
    {
        "sw_ingest_project",
        "sw_record_decision",
        "sw_report_progress",
        "sw_handoff",
        "sw_resume_task",
        "sw_complete_task",
    }
)


def load_dotenv(path: Path) -> dict[str, str]:
    """Flat KEY=VALUE reader; a missing file degrades to {} (rule mode)."""
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    return env


def plan_workdir(plan: ExecutionPlan) -> Path:
    """The directory the agent actually works in (checkout + subdir)."""
    root = Path(plan.workspace_dir)
    return root / plan.workspace_subdir if plan.workspace_subdir else root


def build_prompt(
    pack: TaskPack, project_id: str, *, arm: str, hint: str = "flow"
) -> str:
    """The agent prompt: goal, contract, project id, finish line; ON adds
    the tool-usage hint so the arm difference stays 'tools + guidance'."""
    parts = [
        "You are working on the project in the current directory "
        "(git already initialized).",
        f"Goal: {pack.task.goal}",
    ]
    if pack.task.contract:
        parts.append(
            "Minimum interface contract (hidden acceptance tests will "
            f"import exactly these):\n{pack.task.contract}"
        )
    parts.append(f"Project id (use verbatim with any tooling): {project_id}")
    if pack.acceptance.forbidden_regressions:
        parts.append(
            "Behavior that must keep working (regression guard): "
            + ", ".join(pack.acceptance.forbidden_regressions)
        )
    parts.append(
        "Finish by running: python -m pytest -q and make it green."
    )
    prompt = "\n\n".join(parts)
    if arm == "on":
        prompt += HINTS.get(hint, HINTS["flow"])
    return prompt


def invocation_for(
    pack: TaskPack,
    plan: ExecutionPlan,
    *,
    arm: str,
    cfg_path: Path | None,
    hint: str = "flow",
    agent_binary: str | None = None,
) -> tuple[list[str], str]:
    """Resolve (command, prompt) an arm would run. Shared by the real run
    and --dry-run so the preflight can never drift from execution."""
    binary = agent_binary or shutil.which("claude") or "claude"
    if os.name == "nt":
        cmd = ["cmd", "/c", binary]
    else:
        cmd = [binary]
    cmd += [
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--dangerously-skip-permissions",
    ]
    if arm == "on":
        if cfg_path is None:
            raise InvalidRequest("the ON arm requires an MCP config path")
        cmd += ["--mcp-config", str(cfg_path), "--strict-mcp-config"]
    return cmd, build_prompt(pack, plan.project_id, arm=arm, hint=hint)


def mcp_config_for(
    plan: ExecutionPlan,
    *,
    python_exe: str = sys.executable,
    usage_out: Path | str | None = None,
) -> dict[str, Any]:
    """stdio server config for the ON arm; the env is the isolation seam:
    WORKSPACE__ROOT points at this run's checkout, USAGE_OUT captures the
    server-side telemetry that would otherwise die with the process."""
    env = load_dotenv(SPECWEAVER_ROOT / ".env")
    env["WORKSPACE__ROOT"] = str(plan_workdir(plan))
    env["PYTHONPATH"] = str(SPECWEAVER_ROOT / "src")
    # the agent is told to run "python -m pytest"; make sure `python` inside
    # the server process resolves to the project venv
    env["PATH"] = (
        str(Path(python_exe).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    if usage_out is not None:
        env[USAGE_OUT_ENV] = str(usage_out)
    return {
        "mcpServers": {
            "specweaver": {
                "type": "stdio",
                "command": python_exe,
                "args": ["-m", "specweaver.adapters.driving.mcp.run_stdio"],
                "env": env,
            }
        }
    }


def parse_transcript(text: str) -> dict[str, Any]:
    """stream-json events -> sw_calls / usage / num_turns / result_text."""
    result: dict[str, Any] = {"sw_calls": [], "usage": {}, "num_turns": None,
                              "result_text": ""}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        if message.get("role") == "assistant":
            for item in message.get("content", []):
                name = item.get("name", "")
                if name.startswith("mcp__specweaver"):
                    result["sw_calls"].append(
                        name.removeprefix("mcp__specweaver__")
                    )
        if event.get("type") == "result":
            result["num_turns"] = event.get("num_turns")
            result["usage"] = event.get("usage") or {}
            result["result_text"] = str(event.get("result"))[:600]
    return result


def backend_probe(
    timeout: float = 1.0,
    targets: dict[str, tuple[str, int]] | None = None,
) -> dict[str, bool]:
    """TCP reachability of the backends (gate.py's probe, reusable)."""
    real = targets or {
        "seekdb": ("127.0.0.1", 2881),
        "powercontext": ("127.0.0.1", 8000),
    }
    status: dict[str, bool] = {}
    for name, (host, port) in real.items():
        try:
            with socket.create_connection((host, port), timeout=timeout):
                status[name] = True
        except OSError:
            status[name] = False
    return status


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise InvalidRequest(
            f"git {' '.join(args[:2])} failed: {proc.stderr.strip()[:300]}"
        )
    return proc.stdout.strip()


def checkout_pack(
    origin: str,
    commit: str,
    target: Path,
    *,
    subdir: str = "",
    source: str = "",
) -> Path:
    """Clone (from ``source`` mirror when given) and checkout ``commit``;
    returns the workdir the agent edits. The clone is a real repo, so the
    judge's diff is a true git diff against the pinned commit."""
    upstream = source or origin
    # a backslashed Windows drive path reads as SCP syntax (host=E) to git;
    # forward slashes are unambiguous for local clones
    if len(upstream) > 2 and upstream[1] == ":":
        upstream = upstream.replace("\\", "/")
    if Path(target).exists():
        raise InvalidRequest(f"{target}: checkout target already exists")
    proc = subprocess.run(
        ["git", "clone", "-q", upstream, str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise InvalidRequest(
            f"clone {upstream} failed: {proc.stderr.strip()[:300]}"
        )
    try:
        _git(target, "checkout", "-q", commit)
        _git(target, "config", "user.name", "run-eval-harness")
        _git(target, "config", "user.email", "harness@specweaver.local")
    except InvalidRequest:
        shutil.rmtree(target, ignore_errors=True)
        raise
    root = Path(target)
    return root / subdir if subdir else root


def resolve_pack_relative(pack_file: Path, rel: str) -> Path:
    """Resolve a manifest-relative path with a traversal guard: the result
    must stay inside the manifest's own directory (a manifest is machine-read
    input and must not reach arbitrary files)."""
    base = Path(pack_file).resolve().parent
    resolved = (base / rel).resolve()
    if base not in resolved.parents:
        raise InvalidRequest(
            f"path must live under the manifest directory, got {rel!r}"
        )
    return resolved


def hidden_suite_source(pack_file: Path, pack: TaskPack) -> Path | None:
    """Resolve the pack-relative hidden suite; None when the pack has none."""
    if not pack.acceptance.hidden_suite:
        return None
    suite = resolve_pack_relative(pack_file, pack.acceptance.hidden_suite)
    if not suite.is_file():
        raise InvalidRequest(
            f"{pack.id}: hidden suite not found at {suite}"
        )
    return suite


def stage_given_files(
    pack_file: Path, pack: TaskPack, workdir: Path
) -> list[str]:
    """Copy given_files into the workspace (dest relative to workdir).

    Given files are the pack's authored inputs — e.g. a pending-change delta
    the task builds upon — and land BEFORE the agent starts, so ingestion
    treats them as first-class workspace content. Returns the staged
    workspace-relative destinations.
    """
    staged: list[str] = []
    for given in pack.task.given_files:
        src = resolve_pack_relative(pack_file, given.src)
        if not src.is_file():
            raise InvalidRequest(
                f"{pack.id}: given file not found at {src}"
            )
        dest = workdir / given.dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
        staged.append(given.dest)
    return staged


def command_env(python_exe: str) -> dict[str, str]:
    """Shell environment for workspace commands: `python` resolves to the
    project venv so declared commands like "python -m pytest" work."""
    env = os.environ.copy()
    env["PATH"] = (
        str(Path(python_exe).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    return env


def run_workspace_commands(
    workdir: Path,
    commands: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_s: float | None = None,
    report_dir: Path | None = None,
    report_prefix: str = "cmd",
) -> list[dict[str, Any]]:
    """Run shell commands in order inside workdir; one result dict each.
    Shared by acceptance judging and environment setup."""
    results: list[dict[str, Any]] = []
    for index, command in enumerate(commands):
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
            tail = (proc.stdout + proc.stderr)[-400:]
            exit_code: int | None = proc.returncode
        except subprocess.TimeoutExpired:
            tail = f"timeout after {timeout_s}s"
            exit_code = None
        entry: dict[str, Any] = {
            "command": command,
            "exit_code": exit_code,
            "summary": tail.splitlines()[-1] if tail else "",
        }
        if report_dir is not None:
            report = report_dir / f"{report_prefix}-{index}.txt"
            report.write_text(tail, encoding="utf-8")
            entry["report_ref"] = report.name
        results.append(entry)
    return results


def normalize_arms(value: str) -> list[str]:
    """Validate the --arms list; unknown or empty values fail loudly instead
    of silently degrading an arm to 'no MCP, no hint'."""
    arms = [a.strip().lower() for a in (value or "").split(",") if a.strip()]
    if not arms:
        raise InvalidRequest("arms is empty; expected e.g. 'on,off'")
    unknown = [a for a in arms if a not in ("on", "off")]
    if unknown:
        raise InvalidRequest(
            f"unknown arm(s): {', '.join(unknown)}; expected on/off"
        )
    return arms


def judge_workspace(
    checkout_root: Path,
    workdir: Path,
    base_rev: str,
    outdir: Path,
    *,
    test_commands: list[str],
    hidden_suite: Path | None = None,
    python_exe: str = sys.executable,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Capture the agent diff, then grade: inject the hidden suite (after
    the diff, so it never leaks) and run every acceptance command."""
    if _git(checkout_root, "status", "--porcelain"):
        _git(checkout_root, "add", "-A")
        _git(checkout_root, "commit", "-q", "-m", "agent work")
    head_rev = _git(checkout_root, "rev-parse", "HEAD")
    diff = _git(checkout_root, "diff", base_rev, head_rev)
    outdir.joinpath("agent.diff").write_text(diff, encoding="utf-8")

    if hidden_suite is not None:
        tests_dir = workdir / "tests"
        tests_dir.mkdir(exist_ok=True)
        shutil.copy(hidden_suite, tests_dir / hidden_suite.name)

    results = run_workspace_commands(
        workdir,
        test_commands,
        env=command_env(python_exe),
        timeout_s=timeout_s,
        report_dir=outdir,
        report_prefix="judge",
    )
    changed = diff.strip() != ""
    return {
        "changed": changed,
        "results": results,
        "success": changed and all(r["exit_code"] == 0 for r in results),
    }


def read_server_usage(csv_path: Path) -> dict[str, float]:
    """Sum the SPECWEAVER_USAGE_OUT export into EvalRun-usage numbers."""
    if not csv_path.is_file():
        return {}
    import csv

    totals = {"llm_calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
              "backend_calls": 0}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            totals["llm_calls"] += int(row.get("llm_calls") or 0)
            totals["prompt_tokens"] += int(row.get("prompt_tokens") or 0)
            totals["completion_tokens"] += int(
                row.get("completion_tokens") or 0
            )
            totals["backend_calls"] += int(row.get("backend_calls") or 0)
    return {key: float(value) for key, value in totals.items()}
