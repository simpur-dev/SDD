"""Build the ``minimax/`` submission payload from the working tree.

The official brief (2026-10-26) requires the delivered materials to live in
the competition repository's ``minimax/`` directory and be evaluated at a
fixed commit.  This script assembles a self-contained copy of what reviewers
need: the SpecWeaver package (source, scripts, deploy, templates, taskpacks,
tests), the railway validation project and the evidence directories that the
technical-usage record references.

It intentionally excludes local-only material: ``.env`` files (except the
example), caches, ``.deps``, ``research/``, ``demo/openspec-demo/`` and the
generated ``minimax/source`` itself.

Usage:
    python specweaver/scripts/build_submission.py            # write minimax/source/
    python specweaver/scripts/build_submission.py --dry-run  # list what would be copied
    python specweaver/scripts/build_submission.py --dest /tmp/pkg  # alternate target
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPECWEAVER = ROOT / "specweaver"
DEFAULT_DEST = ROOT / "minimax" / "source"

_EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".deps",
    "node_modules",
    ".git",
    "dist",
    "build",
    "htmlcov",
}
_EXCLUDE_FILES = {".coverage", ".env"}
_EVIDENCE_GLOBS = (
    "minimax-dev-*",
    "official-spec-reimport-*",
    "official-state-reuse-*",
    "official-clean-env-*",
)

_README = """# source/ 使用说明（自动生成）

本目录由 `specweaver/scripts/build_submission.py` 生成，是正式题面要求的
`minimax/` 提交材料中的“完整源码 + 配套程序 + 验证工程 + 证据”。

- `pyproject.toml` / `src/specweaver/` / `scripts/` / `deploy/` /
  `templates/` / `taskpacks/` / `tests/`：上下文模块源码与配套程序；
- `demo/railway/`：验证样例工程（Python + pytest，全部文件随包）；
- `evidence/`：技术使用记录引用的原始证据（MiniMax 开发记录、规格重导入、状态重启复用）。

运行方式见上级目录的 `运行说明.md`；验证流程见 `验证样例.md`。
"""


def _ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in _EXCLUDE_DIRS or name in _EXCLUDE_FILES:
            ignored.add(name)
        elif name.startswith(".env.") and name != ".env.example":
            ignored.add(name)
    return ignored


def _count_files(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name in _EXCLUDE_FILES:
            continue
        if path.name.startswith(".env.") and path.name != ".env.example":
            continue
        total += 1
    return total


def _plan() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for name in ("pyproject.toml", "README.md", ".env.example"):
        pairs.append((SPECWEAVER / name, Path(name)))
    for name in ("src", "scripts", "deploy", "templates", "taskpacks", "tests"):
        pairs.append((SPECWEAVER / name, Path(name)))
    pairs.append((ROOT / "demo" / "railway", Path("demo") / "railway"))
    evidence_root = ROOT / "evidence"
    for pattern in _EVIDENCE_GLOBS:
        for source in sorted(evidence_root.glob(pattern)):
            if source.is_dir():
                pairs.append((source, Path("evidence") / source.name))
    return pairs


def build(dest: Path, *, dry_run: bool) -> dict[str, int]:
    target = Path(dest)
    pairs = _plan()
    missing = [str(src) for src, _ in pairs if not src.exists()]
    if missing:
        raise SystemExit("missing source paths:\n" + "\n".join(missing))
    planned_files = sum(
        _count_files(src) if src.is_dir() else 1 for src, _ in pairs
    )
    if dry_run:
        for src, rel in pairs:
            print(f"{src.relative_to(ROOT)} -> {rel}")
        print(f"dry-run: {len(pairs)} entries, ~{planned_files} files")
        return {"entries": len(pairs), "files": planned_files}
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for src, rel in pairs:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, ignore=_ignore)
        else:
            shutil.copy2(src, dst)
    (target / "README.md").write_text(_README, encoding="utf-8")
    actual = sum(1 for path in target.rglob("*") if path.is_file())
    size_mb = sum(p.stat().st_size for p in target.rglob("*") if p.is_file()) / (
        1024 * 1024
    )
    print(f"built {target}: {actual} files, {size_mb:.1f} MB")
    return {"entries": len(pairs), "files": actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default=str(DEFAULT_DEST),
        help="target directory (default: minimax/source)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="list the plan, copy nothing"
    )
    args = parser.parse_args()
    build(Path(args.dest), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
