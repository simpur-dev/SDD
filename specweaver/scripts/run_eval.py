"""TaskPack-driven evaluation harness (docs/01 §10.6/§11.2).

Reads a TaskPack, runs the same task per arm (OFF = plain workspace, ON =
SpecWeaver MCP tools) against a real coding agent, grades via the pack's
acceptance commands plus its hidden suite, and emits one EvalRun per run.
All decisions (checkout, config, invocation, prompt, parsing, judging) live
in specweaver.evaluation.harness and are unit-tested there; this script only
orchestrates.

Usage:
    python scripts/run_eval.py <taskpack.json> [--arms on,off] [--n 1]
        [--timeout 900] [--source <local mirror repo>] [--hint flow|full]
        [--start-backends] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECWEAVER_ROOT = Path(__file__).resolve().parents[1]

from specweaver.evaluation.artifact import (  # noqa: E402
    AgentRef,
    CodeDiff,
    EvalMeta,
    MemoryOp,
    OutcomeBlock,
    TestEvidence,
    UsageBlock,
    build_evalrun,
)
from specweaver.evaluation.harness import (  # noqa: E402
    MEMORY_TOOLS,
    backend_probe,
    checkout_pack,
    hidden_suite_source,
    invocation_for,
    judge_workspace,
    mcp_config_for,
    parse_transcript,
)
from specweaver.evaluation.taskpack import (  # noqa: E402
    ExecutionPlan,
    TaskPack,
    load_pack,
    materialize,
)
from specweaver.shared.errors import InvalidRequest  # noqa: E402


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def _ensure_backends(start: bool) -> None:
    probe = backend_probe()
    if all(probe.values()):
        return
    if not start:
        down = ", ".join(name for name, ok in probe.items() if not ok)
        raise InvalidRequest(
            f"backends unreachable: {down} — start deploy/docker-compose.yml "
            "(or pass --start-backends)"
        )
    script = SPECWEAVER_ROOT / "deploy" / "wsl" / "wait_ready.sh"
    print(f"[harness] starting backends via {script} ...")
    script_wsl = "/mnt/" + SPECWEAVER_ROOT.drive.lower() + "/" + (
        SPECWEAVER_ROOT.relative_to(SPECWEAVER_ROOT.anchor).as_posix()
    )
    subprocess.run(
        ["wsl", "bash", "-lc",
         f"cd '{script_wsl}/deploy/wsl' && bash wait_ready.sh"],
        check=False,
    )
    probe = backend_probe(timeout=5.0)
    if not all(probe.values()):
        down = ", ".join(name for name, ok in probe.items() if not ok)
        raise InvalidRequest(f"backends still unreachable after start: {down}")


def spawn_keepalive(seconds: int):
    """Hold the WSL VM open so the docker stack cannot be idle-torn-down
    mid-run (see deploy/README.md). The harness owns and reaps this
    process; the VM also stays up for any other session meanwhile."""
    print(f"[harness] holding WSL VM open for {seconds}s (docker keepalive)")
    return subprocess.Popen(
        ["wsl", "bash", "-lc", f"sleep {seconds}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _dry_run(pack: TaskPack, pack_file: Path, args: argparse.Namespace) -> None:
    """Resolve everything a run would execute; launch nothing, spend nothing."""
    suite = hidden_suite_source(pack_file, pack)
    plan_lines = []
    for arm in [a.strip() for a in args.arms.split(",") if a.strip()]:
        plan = materialize(pack, f"{arm}-0-preview", workroot="(temp)")
        cmd, prompt = invocation_for(
            pack, plan, arm=arm,
            cfg_path=Path("(temp)/mcp.json") if arm == "on" else None,
            hint=args.hint,
        )
        entry = {
            "arm": arm,
            "project_id": plan.project_id,
            "scope_title": plan.scope_title,
            "workspace_dir": plan.workspace_dir,
            "workspace_subdir": plan.workspace_subdir,
            "clone_from": args.source or pack.repo.origin,
            "pinned_commit": pack.repo.commit,
            "profile": plan.profile,
            "agent_binary": shutil.which("claude") or "(not on PATH)",
            "cmd": cmd,
            "prompt_chars": len(prompt),
            "prompt_tail": prompt[-220:],
            "test_commands": pack.acceptance.test_commands,
            "hidden_suite": str(suite) if suite else "(none)",
        }
        if arm == "on":
            entry["mcp_env_keys"] = sorted(
                mcp_config_for(plan, usage_out="(outdir)/server-usage.csv")[
                    "mcpServers"
                ]["specweaver"]["env"]
            )
        plan_lines.append(entry)
    print(json.dumps(plan_lines, ensure_ascii=False, indent=2))
    print("dry-run only: no agent launched, no inference spent")


def _run_one(
    pack: TaskPack,
    pack_file: Path,
    plan: ExecutionPlan,
    arm: str,
    index: int,
    outdir: Path,
    args: argparse.Namespace,
) -> dict:
    """One agent run: checkout → agent → judge → EvalRun. Never raises."""
    record: dict = {"arm": arm, "run": index, "project_id": plan.project_id}
    suite = hidden_suite_source(pack_file, pack)
    temp = Path(plan.workspace_dir).parent
    try:
        workdir = checkout_pack(
            pack.repo.origin,
            pack.repo.commit,
            Path(plan.workspace_dir),
            subdir=plan.workspace_subdir,
            source=args.source,
        )
        checkout_root = Path(plan.workspace_dir)
        base_rev = pack.repo.commit

        cfg_path = None
        usage_out = outdir / "server-usage.csv"
        if arm == "on":
            cfg_path = temp / "mcp.json"
            cfg_path.write_text(
                json.dumps(
                    mcp_config_for(plan, usage_out=usage_out)
                ),
                encoding="utf-8",
            )
        cmd, prompt = invocation_for(
            pack, plan, arm=arm, cfg_path=cfg_path, hint=args.hint
        )
        outdir.joinpath("prompt.txt").write_text(prompt, encoding="utf-8")

        started = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            transcript = proc.stdout
            record["rc"] = proc.returncode
            if proc.stderr.strip():
                (outdir / "claude-stderr.txt").write_text(
                    proc.stderr[-4000:], encoding="utf-8"
                )
        except subprocess.TimeoutExpired as exc:
            transcript = exc.stdout or "" if isinstance(exc.stdout, str) else ""
            record["error"] = f"timeout after {args.timeout}s"
        (outdir / "transcript.jsonl").write_text(transcript, encoding="utf-8")
        parsed = parse_transcript(transcript)
        record["duration_ms"] = (time.time() - started) * 1000
        record["turns"] = parsed.get("num_turns")

        judge = judge_workspace(
            checkout_root,
            workdir,
            base_rev,
            outdir,
            test_commands=pack.acceptance.test_commands,
            hidden_suite=suite,
        )
        record.update(
            changed=judge["changed"],
            success=judge["success"],
            summary=judge["results"][0]["summary"] if judge["results"] else "",
        )

        server = {}
        if usage_out.exists():
            from specweaver.evaluation.harness import read_server_usage

            server = read_server_usage(usage_out)
        raw_usage = dict(parsed.get("usage") or {})
        usage = UsageBlock(
            prompt_tokens=int(raw_usage.get("input_tokens") or 0)
            + int(server.get("prompt_tokens", 0)),
            completion_tokens=int(raw_usage.get("output_tokens") or 0)
            + int(server.get("completion_tokens", 0)),
            llm_calls=int(server.get("llm_calls", 0)),
            backend_calls=int(server.get("backend_calls", 0)),
            duration_ms=record["duration_ms"],
            agent_usage_raw=raw_usage,
        )
        sw_calls = list(parsed.get("sw_calls") or [])
        record["sw_calls"] = sw_calls
        memory_ops = [
            MemoryOp(action=call) for call in sw_calls if call in MEMORY_TOOLS
        ]
        notes = [f"sw_calls={sw_calls}"]
        if record.get("error"):
            notes.append(record["error"])
        tests = [
            TestEvidence(
                command=result["command"],
                exit_code=result["exit_code"],
                summary=result["summary"],
                report_ref=f"judge-{i}.txt",
            )
            for i, result in enumerate(judge["results"])
        ]
        evalrun = build_evalrun(
            EvalMeta(
                source="run_eval",
                arm=arm if arm in ("off", "on") else "",
                run_index=index,
                agent=AgentRef(
                    name=pack.agent.name,
                    version=pack.agent.version,
                    model=pack.agent.model,
                ),
                sw_version=_git_head(REPO_ROOT),
                taskpack_id=pack.id,
                tier=pack.tier,
            ),
            diff=CodeDiff(diff_refs=["agent.diff"]),
            tests=tests,
            memory_ops=memory_ops,
            usage=usage,
            outcome=OutcomeBlock(
                success=judge["success"], source="judge", notes=notes
            ),
            sources=[
                "transcript.jsonl",
                "agent.diff",
                "prompt.txt",
                *(t.report_ref for t in tests),
                *( ["server-usage.csv"] if usage_out.exists() else [] ),
            ],
            taskpack=pack,
        )
        (outdir / "evalrun.json").write_text(
            evalrun.model_dump_json(indent=2), encoding="utf-8"
        )
        record["evalrun"] = "evalrun.json"
    except Exception as exc:  # noqa: BLE001 - harness must finish the loop
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", help="TaskPack manifest path")
    parser.add_argument("--arms", default="on,off")
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--source",
        default="",
        help="local mirror repo to clone from (must contain the pinned "
        "commit); default: clone pack.repo.origin",
    )
    parser.add_argument("--hint", choices=("flow", "full"), default="flow")
    parser.add_argument(
        "--start-backends",
        action="store_true",
        help="attempt deploy/wsl/wait_ready.sh when the probe fails",
    )
    parser.add_argument("--out", default=str(REPO_ROOT / "evidence"))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve the full execution plan, launch nothing",
    )
    args = parser.parse_args()

    try:
        pack = load_pack(args.pack)
    except InvalidRequest as exc:
        print(f"FAIL {exc.message}")
        return 1
    pack_file = Path(args.pack)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if "on" in arms:
        try:
            _ensure_backends(args.start_backends)
        except InvalidRequest as exc:
            print(f"FAIL {exc.message}")
            return 1

    if args.dry_run:
        _dry_run(pack, pack_file, args)
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = Path(args.out) / f"eval-{pack.id}-{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    keepalive = None
    if "on" in arms:
        keepalive = spawn_keepalive(args.n * args.timeout + 600)
    records = []
    try:
        for arm in arms:
            for index in range(args.n):
                plan = materialize(
                    pack, f"{arm}-{index}-{stamp}",
                    workroot=tempfile.mkdtemp(prefix=f"runeval-{arm}-{index}-"),
                )
                outdir = root / f"{arm}-{index}"
                outdir.mkdir(parents=True, exist_ok=True)
                record = _run_one(
                    pack, pack_file, plan, arm, index, outdir, args
                )
                records.append(record)
                print(
                    f"[{arm} {index}] success={record.get('success')} "
                    f"turns={record.get('turns')} "
                    f"sw={len(record.get('sw_calls', []))} "
                    f"-> {record.get('error', record.get('summary', ''))[:60]}",
                    flush=True,
                )
    finally:
        if keepalive is not None:
            keepalive.terminate()
    (root / "summary.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for r in records if r.get("success"))
    print(f"done -> {root} ({ok}/{len(records)} succeeded)")
    return 0 if ok == len(records) else 1


if __name__ == "__main__":
    sys.exit(main())
