"""OFF/ON comparison harness (docs/01 §11).

Same railway task and same agent (Claude Code), run N times per arm:
OFF = plain workspace; ON = identical workspace plus SpecWeaver MCP tools.
Success is decided by a hidden acceptance suite plus the untouched legacy
tests, so "success rate" means functional fit + no behavior regression.
Writes transcripts, judge results and a markdown report under
<repo>/evidence/off-on/<stamp>/.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEMO = REPO / "demo" / "railway"
SPECWEAVER = REPO / "specweaver"
VENV_PY = sys.executable

TASK_CORE = """You are working on the railway demo project in the current \
directory (small Python + pytest codebase, git already initialized).
Goal: add "adjust departure time per stop" support:
1. src/schedule.py: add adjust_departure(train: Train, new_start: str) -> Train
   returning a NEW Train whose start becomes new_start with legs unchanged \
(the whole timetable shifts).
2. src/api.py: add submit_adjust_departure(train: Train, new_start: str) -> \
dict[str, str] returning the adjusted arrival times.
3. Keep every existing test passing; do not regress any current behavior.
4. Add regression tests for the new behavior, including one showing an \
adjusted train is still blocked from publishing when it conflicts with an \
existing vehicle-occupation window.
Project id (use verbatim with any tooling): {pid}
Finish by running: python -m pytest -q   and make it green."""

TASK_HARD = """You are working on the railway demo project in the current \
directory (small Python + pytest codebase, git already initialized).
Goal: dispatchers must be able to ADJUST A TRAIN'S DEPARTURE TIME so that \
all later stop times recalculate, without breaking anything that exists \
today. The competition rules require the full chain to keep working after \
the change (timetable calculation, vehicle-occupation re-check, publish \
gating) and the whole test suite must stay green.
Minimum interface contract (hidden acceptance tests will import exactly \
these): src/schedule.py gains adjust_departure(train, new_start) -> Train \
and src/api.py gains submit_adjust_departure(train, new_start) -> dict of \
stop -> "HH:MM".
Project id (use verbatim with any tooling): {pid}
Before coding, gather the relevant project context (specs, rules, \
existing tests) however you see fit. Finish by running \
python -m pytest -q and make it green."""

ON_HINT = """

This workspace provides SpecWeaver MCP tools (mcp__specweaver__sw_*).
Recommended flow: sw_ingest_project (project id above), then sw_get_context \
(project id + this task) BEFORE editing; honor the constraints and findings \
it reports (rules, conflicts, gaps, stale specs). After tests are green, \
call sw_complete_task with base_ref = the git HEAD captured BEFORE your \
edits and test_command "python -m pytest -q"."""

ACCEPTANCE = '''"""Hidden acceptance suite injected by the OFF/ON harness."""

from api import submit_adjust_departure
from occupancy import Occupation
from publish import can_publish
from schedule import Train, adjust_departure, arrival_times


def _train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_adjust_shifts_whole_timetable() -> None:
    after = arrival_times(adjust_departure(_train(), "08:30"))
    assert after == {"A": "08:30", "B": "08:40", "C": "08:55"}


def test_api_entry_returns_adjusted_times() -> None:
    assert submit_adjust_departure(_train(), "09:00")["C"] == "09:25"


def test_adjusted_train_still_blocked_on_conflict() -> None:
    adjusted = adjust_departure(_train(), "08:05")
    ok, _ = can_publish(adjusted, [Occupation("K1", 486, 494)])
    assert not ok
'''


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True,
    ).stdout.strip()


def inference_env() -> dict[str, str]:
    """Inference settings to hand the ON-arm server, absent .env tolerated.

    A fresh clone has no credentials: returning {} keeps the harness usable
    in rule mode instead of dying on FileNotFoundError mid-comparison.
    """
    path = SPECWEAVER / ".env"
    if not path.exists():
        print(f"[warn] no {path}; ON arm runs without inference credentials")
        return {}
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value
    return env


def prepare(workdir: Path) -> str:
    shutil.copytree(
        DEMO, workdir,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    git(workdir, "init", "-q")
    git(workdir, "config", "user.name", "off-on-harness")
    git(workdir, "config", "user.email", "harness@specweaver.local")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", "baseline")
    return git(workdir, "rev-parse", "HEAD")


def mcp_config(workdir: Path, path: Path) -> None:
    env = inference_env()
    env["WORKSPACE__ROOT"] = str(workdir)
    env["PYTHONPATH"] = str(SPECWEAVER / "src")
    # the agent is told to use "python -m pytest"; make sure `python`
    # inside the server process resolves to the project venv
    env["PATH"] = (
        str(Path(VENV_PY).parent) + os.pathsep + os.environ.get("PATH", "")
    )
    config = {
        "mcpServers": {
            "specweaver": {
                "type": "stdio",
                "command": VENV_PY,
                "args": [
                    "-m", "specweaver.adapters.driving.mcp.run_stdio",
                ],
                "env": env,
            }
        }
    }
    path.write_text(json.dumps(config), encoding="utf-8")


def run_agent(arm: str, workdir: Path, pid: str, outdir: Path,
              cfg: Path, timeout: int, task: str) -> dict:
    prompt = (
        (TASK_HARD if task == "hard" else TASK_CORE).format(pid=pid)
        + (ON_HINT if arm == "on" else "")
    )
    cmd = [
        "cmd", "/c", shutil.which("claude") or "claude",
        "-p", "--output-format", "stream-json", "--verbose",
        "--dangerously-skip-permissions",
    ]
    if arm == "on":
        cmd += ["--mcp-config", str(cfg), "--strict-mcp-config"]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd, cwd=workdir, input=prompt, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s",
                "duration_ms": timeout * 1000.0}
    (outdir / "transcript.jsonl").write_text(proc.stdout, encoding="utf-8")
    if proc.stderr.strip():
        (outdir / "claude-stderr.txt").write_text(
            proc.stderr[-4000:], encoding="utf-8"
        )
    result: dict = {"rc": proc.returncode, "sw_calls": [], "usage": {},
                    "duration_ms": (time.time() - started) * 1000}
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        if message.get("role") == "assistant":
            for item in message.get("content", []):
                name = item.get("name", "")
                if name.startswith("mcp__specweaver"):
                    result["sw_calls"].append(name.removeprefix(
                        "mcp__specweaver__"))
        if event.get("type") == "result":
            result["num_turns"] = event.get("num_turns")
            result["usage"] = event.get("usage") or {}
            result["result_text"] = str(event.get("result"))[:600]
    return result


def judge(workdir: Path, base_rev: str, outdir: Path) -> dict:
    if git(workdir, "status", "--porcelain"):
        git(workdir, "add", "-A")
        git(workdir, "commit", "-q", "-m", "agent work")
    head_rev = git(workdir, "rev-parse", "HEAD")
    diff = git(workdir, "diff", base_rev, head_rev)
    (outdir / "agent.diff").write_text(diff, encoding="utf-8")
    (workdir / "tests" / "test_acceptance.py").write_text(
        ACCEPTANCE, encoding="utf-8"
    )
    proc = subprocess.run(
        [VENV_PY, "-m", "pytest", "-q"], cwd=workdir,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    tail = (proc.stdout + proc.stderr)[-400:]
    outdir.joinpath("judge.txt").write_text(tail, encoding="utf-8")
    return {
        "changed": diff.strip() != "",
        "pytest_rc": proc.returncode,
        "summary": tail.splitlines()[-1] if tail else "",
        "success": proc.returncode == 0 and diff.strip() != "",
    }


def mean(values: list[float]) -> float:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else 0.0


def median(values: list[float]) -> float:
    """Robust central tendency - with N=3 one outlier moves the mean a lot."""
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 1)


def write_report(root: Path, runs: list[dict], n: int,
               task_label: str) -> None:
    lines = [
        "# OFF/ON 对比报告（docs/01 §11）",
        "",
        f"- 生成：{time.strftime('%Y-%m-%d %H:%M:%S')}；每臂 N={n}；"
        f"任务档位：{task_label}",
        "- 开发 Agent：Claude Code（后端 deepseek-flash，非交互 "
        "`-p --output-format stream-json`，`--dangerously-skip-permissions`"
        "，工作副本为一次性临时 git 仓库）",
        "- ON 臂差异：同一任务提示 + SpecWeaver MCP 工具（provider="
        "qianwen：qwen-flash 规划 + text-embedding-v4@1536 语义向量）"
        "与推荐流程提示；OFF 臂无工具、无该提示",
        "- 判据（对 Agent 隐藏，任务结束后注入）：3 条验收测试 + 全部"
        "遗留测试必须通过 + 有实际代码变更；success = 全部满足",
        "",
        "| 臂 | 成功率 | 中位耗时(s) | 均值耗时(s) | 最快/最慢(s) |"
        " 中位轮数 | 中位 out tokens | 均值 out tokens | 中位 sw 调用 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in ("off", "on"):
        rows = [r for r in runs if r["arm"] == arm]
        if not rows:
            continue
        ok = sum(1 for r in rows if r.get("success"))
        usage = [(r.get("usage") or {}) for r in rows]
        tout = [u.get("output_tokens", 0) or 0 for u in usage]
        durations = [r.get("duration_ms", 0) / 1000 for r in rows]
        lines.append(
            f"| {arm.upper()} | {ok}/{len(rows)} "
            f"| {median(durations)} | {mean(durations)} "
            f"| {round(min(durations), 1)}/{round(max(durations), 1)} "
            f"| {median([r.get('num_turns') or 0 for r in rows])} "
            f"| {median(tout)} | {mean(tout)} "
            f"| {median([len(r.get('sw_calls', [])) for r in rows])} |"
        )
    lines += ["", "## 每次运行明细", ""]
    for r in runs:
        lines.append(
            f"- **{r['arm'].upper()}-{r['run']}** success={r.get('success')} "
            f"turns={r.get('num_turns')} "
            f"sw={r.get('sw_calls') or []} "
            f"judge={r.get('summary', r.get('error', ''))}"
        )
    lines += [
        "",
        "## 局限性（如实声明）",
        "",
        "- 单任务、小样本（N 见头部），统计意义有限，趋势参考；",
        "- ON 臂附带推荐流程提示（工具使用引导），差异包含'工具存在+使用"
        "指引'两因素，非纯上下文增益；",
        "- Agent 后端为 deepseek-flash（赛题不限定模型品牌）；",
        "- 两臂同机同仓库副本顺序执行，外部网络/容器状态波动计入耗时。",
        "",
    ]
    (root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--arms", default="off,on")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--out", default=str(REPO / "evidence" / "off-on"))
    parser.add_argument("--task", choices=("easy", "hard"),
                        default="easy")
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = Path(args.out) / stamp
    root.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        for i in range(args.n):
            pid = f"offon-{arm}-{i}-{stamp}"
            temp = Path(tempfile.mkdtemp(prefix=f"offon-{arm}-{i}-"))
            workdir = temp / "railway"
            outdir = root / f"{arm}-{i}"
            outdir.mkdir(parents=True, exist_ok=True)
            record: dict = {"arm": arm, "run": i, "project_id": pid}
            try:
                base_rev = prepare(workdir)
                cfg = temp / "mcp.json"
                mcp_config(workdir, cfg)
                record.update(run_agent(
                    arm, workdir, pid, outdir, cfg, args.timeout,
                    args.task,
                ))
                record.update(judge(workdir, base_rev, outdir))
            except Exception as exc:  # noqa: BLE001 - harness must finish
                record["error"] = f"{type(exc).__name__}: {exc}"[:300]
            finally:
                shutil.rmtree(temp, ignore_errors=True)
            runs.append(record)
            print(f"[{arm} {i}] success={record.get('success')} "
                  f"turns={record.get('num_turns')} "
                  f"sw={len(record.get('sw_calls', []))} "
                  f"-> {record.get('error', record.get('summary', ''))[:60]}",
                  flush=True)
    (root / "summary.json").write_text(
        json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_report(root, runs, args.n, args.task)
    print(f"done -> {root}")


if __name__ == "__main__":
    main()
