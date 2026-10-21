"""Validate TaskPack manifests and preview their execution plans.

Standalone entry for the evaluation assets (no MCP tool, no CLI command —
docs/03 §16 keeps the runtime surface clean). Exits 1 when any manifest is
invalid or a requested commit check fails.

Usage:
    python scripts/taskpack_check.py                 # all packs in taskpacks/
    python scripts/taskpack_check.py path/to/pack.json
    python scripts/taskpack_check.py --plan          # + ExecutionPlan JSON
    python scripts/taskpack_check.py --verify-commit # git-check local origins
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # specweaver/
DEFAULT_PACKS = ROOT / "taskpacks"

from specweaver.evaluation.taskpack import (  # noqa: E402
    TaskPack,
    load_dir,
    load_pack,
    materialize,
)
from specweaver.shared.errors import InvalidRequest  # noqa: E402


def _is_remote(origin: str) -> bool:
    return "://" in origin or origin.startswith("git@")


def _verify_commit(pack: TaskPack) -> tuple[bool, str]:
    """Commit existence for locally reachable origins; remotes are the
    harness's job (it clones before running)."""
    if _is_remote(pack.repo.origin):
        return True, "deferred to harness (remote origin)"
    probe = subprocess.run(
        [
            "git",
            "-C",
            pack.repo.origin,
            "cat-file",
            "-e",
            f"{pack.repo.commit}^{{commit}}",
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return True, "ok"
    return False, f"commit not found in {pack.repo.origin}: {probe.stderr.strip()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="manifest files to check; default: every *.json in taskpacks/",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="also print each pack's materialized ExecutionPlan",
    )
    parser.add_argument(
        "--verify-commit",
        action="store_true",
        help="git-verify pinned commits for locally reachable origins",
    )
    parser.add_argument("--run-id", default="preview")
    parser.add_argument(
        "--workroot",
        default=str(ROOT.parent / "evidence" / "taskpack-preview"),
    )
    args = parser.parse_args()

    try:
        packs = (
            [load_pack(path) for path in args.paths]
            if args.paths
            else load_dir(DEFAULT_PACKS)
        )
    except InvalidRequest as exc:
        print(f"FAIL {exc.message}")
        return 1

    failures = 0
    for pack in packs:
        notes: list[str] = []
        ok = True
        if args.verify_commit:
            commit_ok, note = _verify_commit(pack)
            notes.append(f"commit={note}")
            ok = commit_ok
        print(f"{pack.id} [{pack.tier}] {'OK' if ok else 'FAIL'} {' '.join(notes)}")
        if not ok:
            failures += 1
        if args.plan:
            plan = materialize(pack, args.run_id, args.workroot)
            print(json.dumps(plan.summary(), ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
