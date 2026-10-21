"""Emit EvalRun JSON from existing evidence directories.

Read-only aggregation: writes ``evalrun.json`` next to the evidence it
indexes (per run subdirectory for off-on layouts) and refuses to overwrite
an existing file unless ``--force`` is given.

Usage:
    python scripts/emit_evalrun.py <evidence_dir>... [--taskpack <pack.json>]
        [--agent-name ...] [--agent-version ...] [--sw-version ...] [--force]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # SDD repo root

from specweaver.evaluation.artifact import (  # noqa: E402
    AgentRef,
    collect_demo,
    collect_off_on,
    detect_layout,
)
from specweaver.evaluation.taskpack import load_pack  # noqa: E402
from specweaver.shared.errors import InvalidRequest  # noqa: E402

DEMO_AGENT = "run_demo (scripted steps)"
OFF_ON_AGENT = "claude-code"


def _default_sw_version() -> str:
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return probe.stdout.strip() if probe.returncode == 0 else ""


def _emit_one(
    directory: Path,
    agent: AgentRef,
    taskpack,
    sw_version: str,
) -> list[tuple[Path, object, str]]:
    """Aggregate ``directory`` into (output_path, EvalRun, label) triples.

    Raises InvalidRequest on unrecognized layouts or unreadable evidence.
    """
    layout = detect_layout(directory)
    if layout == "off-on":
        runs = collect_off_on(
            directory, agent=agent, sw_version=sw_version, taskpack=taskpack
        )
        return [
            (
                directory / f"{run.meta.arm}-{run.meta.run_index}" / "evalrun.json",
                run,
                f"{run.meta.arm}-{run.meta.run_index}",
            )
            for run in runs
        ]
    run = collect_demo(
        directory, agent=agent, sw_version=sw_version, taskpack=taskpack
    )
    return [(directory / "evalrun.json", run, layout)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="evidence directories")
    parser.add_argument(
        "--taskpack",
        default="",
        help="attach a TaskPack: fills taskpack_id/tier and the declared "
        "budget side of the comparison",
    )
    parser.add_argument("--agent-name", default="")
    parser.add_argument("--agent-version", default="")
    parser.add_argument(
        "--sw-version",
        default="",
        help="tooling version stamped into meta; default: git HEAD",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing evalrun.json (evidence is never touched)",
    )
    args = parser.parse_args()

    taskpack = None
    if args.taskpack:
        try:
            taskpack = load_pack(args.taskpack)
        except InvalidRequest as exc:
            print(f"FAIL {exc.message}")
            return 1

    sw_version = args.sw_version or _default_sw_version()
    failures = 0
    for raw in args.paths:
        directory = Path(raw)
        try:
            layout = detect_layout(directory)
            if layout == "off-on":
                agent = AgentRef(
                    name=args.agent_name or OFF_ON_AGENT,
                    version=args.agent_version,
                    model="",
                )
            else:
                agent = AgentRef(
                    name=args.agent_name or DEMO_AGENT,
                    version=args.agent_version,
                    model="",
                )
            outputs = _emit_one(directory, agent, taskpack, sw_version)
        except InvalidRequest as exc:
            print(f"FAIL {directory}: {exc.message}")
            failures += 1
            continue
        for out, run, label in outputs:
            if out.exists() and not args.force:
                print(f"SKIP {out}: already exists (use --force to overwrite)")
                failures += 1
                continue
            out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
            print(f"OK   {out}  [{label}]")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
