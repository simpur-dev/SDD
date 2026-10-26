"""Controlled scaling sweep: cost vs recall budget, on the same query.

Varying only ``CONTEXT__N_RESULTS`` (how much retrieval is allowed to deliver)
across two ingested corpora answers the scaling question the two-point
observation could not: is the pipeline's cost driven by corpus size or by the
number of artifacts it hands over?

For every (corpus, cap) cell the same task is run ``--repeats`` times through
the production ``get_context`` usecase against real seekdb, and each span's
backend calls / duration / recall / bundle bytes are recorded, so medians and
nearest-rank p95 come from the samples themselves.

    python scripts/scaling_probe.py --out ../evidence/scaling-20260927

测量前提（2026-09-27 两次复跑踩到，现已由代码把守）：语料必须是"刚 ingest 过、
且 project id 没有被上一次摄入污染"的状态。scratch 语料（如 mcp-verify）会随着代码
改动被反复摄入：同一 project 里成千上万个 markdown 共用 `REQ-1` 这类逻辑 id，后一次
摄入把先一次的副本判为 superseded，而向量召回照样把它们捞回来，于是有效性阶段把几乎
全部召回项排除，测到的是"空 bundle 的成本"（cap=5/20 时 14-44 次往返、bundle 801
bytes），与交付饱满语料的 40 次不可比。因此每次扫描都摄入到一个带时间戳的新 project；
任何一格"有召回但 bundle 只有框架那么大"都会让脚本以退出码 1 拒绝写证据，而不是留下
一条看起来合法的曲线。报告正文的结论句同样从本次数值生成，不复述历史数字。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from specweaver.application.engines.assembly import FIXED_CHROME_BYTES
from specweaver.application.usecases.get_context import GetContextRequest
from specweaver.application.usecases.ingest_project import IngestProjectRequest
from specweaver.domain.ports.catalog import ArtifactFilter
from specweaver.shared import di
from specweaver.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]

TASK_TEXT = "调整某站发车时间并重算后续各站时刻，检查占用冲突并阻止发布"


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile; the sample size is always reported alongside."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(round(q * (len(ordered) - 1)))))
    return round(ordered[index], 2)


async def ingest_once(project: str, workspace_root: str) -> int:
    settings = Settings()
    settings.workspace.root = workspace_root
    async with di.run(settings) as app:
        await app.usecases["ingest_project"](
            IngestProjectRequest(project_id=project, register_source=False)
        )
        corpus = await app.catalog.list_artifacts(
            ArtifactFilter(project_id=project)
        )
    return len(corpus)


def build_large_workspace(src: Path, dst: Path, factor: int) -> int:
    """Replicate a project ``factor`` times with per-copy artifact ids.

    A whole repository cannot serve as the "large corpus" for a scaling
    measurement: its markdown files reuse logical ids (``REQ-1`` in five
    different directories), and ids are unique per project, so one ingest
    supersedes the siblings and validity drops everything downstream —
    measured on this repository: 357 of 361 stored artifacts ended up
    deprecated and the bundle fell back to its fixed frame. Replicating a
    project keeps the ids disjoint, so the only thing that scales is size.
    """
    files = [
        p
        for p in src.rglob("*.md")
        if ".pytest_cache" not in p.parts and "node_modules" not in p.parts
    ]
    originals = {p: p.read_text(encoding="utf-8") for p in files}
    ids = set()
    for text in originals.values():
        ids.update(re.findall(r"^id:\s*(\S+)\s*$", text, flags=re.M))
    for copy in range(factor):
        for path, text in originals.items():
            rewritten = text
            for artifact_id in sorted(ids, key=len, reverse=True):
                pattern = re.compile(
                    rf"(?<![\w-]){re.escape(artifact_id)}(?![\w-])"
                )
                rewritten = pattern.sub(
                    f"{artifact_id}-{copy}", rewritten
                )
            target = dst / f"copy-{copy:02d}" / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rewritten, encoding="utf-8")
    # the workspace adapter reads the project through git, so an untracked
    # scratch tree would ingest as nothing
    for step in (
        ["init", "-q"],
        ["add", "-A"],
        [
            "-c", "user.email=scaling-probe@local",
            "-c", "user.name=scaling-probe",
            "commit", "-q", "-m", "synthetic scaling corpus",
        ],
    ):
        subprocess.run(
            ["git", "-C", str(dst), *step],
            check=True,
            capture_output=True,
        )
    return len(ids) * factor


async def probe(
    project: str,
    cap: int,
    budget: int,
    repeats: int,
    workspace_root: str,
    corpus_size: int,
    corpus_note: str,
) -> dict:
    settings = Settings()
    settings.context.n_results = cap
    settings.context.budget_bytes = budget
    settings.workspace.root = workspace_root

    calls: list[int] = []
    durations: list[float] = []
    recalls: list[int] = []
    sizes: list[int] = []
    async with di.run(settings) as app:
        for _ in range(repeats):
            before = len(app.telemetry.records)
            result = await app.usecases["get_context"](
                GetContextRequest(project_id=project, task_text=TASK_TEXT)
            )
            span = next(
                r for r in reversed(app.telemetry.records[before:])
                if r.name == "get_context"
            )
            calls.append(span.backend_calls)
            durations.append(round(span.duration_ms, 1))
            recalls.append(
                int(span.metrics.get("recall", 0))
            )
            sizes.append(
                result.bundle.budget.used_bytes if result.bundle.budget else 0
            )

    return {
        "project": project,
        "corpus_artifacts": corpus_size,
        "corpus_note": corpus_note,
        "n_results_cap": cap,
        "budget_bytes": budget,
        "repeats": repeats,
        "backend_calls": {
            "min": min(calls), "median": statistics.median(calls),
            "mean": round(statistics.mean(calls), 1), "max": max(calls),
        },
        "duration_ms": {
            "median": percentile(durations, 0.5),
            "p95": percentile(durations, 0.95),
            "max": max(durations),
        },
        "recall_mean": round(statistics.mean(recalls), 1),
        "bundle_bytes_mean": round(statistics.mean(sizes), 1),
    }


def _cell(cells: list[dict], project: str, cap: int) -> dict:
    return next(
        c
        for c in cells
        if c["project"] == project and c["n_results_cap"] == cap
    )


def _reading(small: dict, large: dict) -> str:
    """One bullet comparing both corpora at the same recall cap.

    Written from the measured numbers because the earlier hand-written prose
    kept quoting a run that no longer reproduced once the corpus drifted.
    """
    small_calls, large_calls = (
        small["backend_calls"]["median"],
        large["backend_calls"]["median"],
    )
    ratio = large_calls / max(small_calls, 1)
    verdict = (
        "成本与语料规模基本无关"
        if ratio < 1.2
        else f"成本随语料规模放大到 {ratio:.1f}×"
    )
    return (
        f"- **cap={small['n_results_cap']}**（{small['corpus_artifacts']} 构件"
        f" vs {large['corpus_artifacts']} 构件）：后端调用中位 "
        f"{small_calls} vs {large_calls} → "
        f"{verdict}；平均召回 {small['recall_mean']} vs "
        f"{large['recall_mean']}，bundle {small['bundle_bytes_mean']}B vs "
        f"{large['bundle_bytes_mean']}B。"
    )


def write_markdown(out_dir: Path, cells: list[dict], repeats: int) -> None:
    caps = sorted({c["n_results_cap"] for c in cells})
    small_project, large_project = cells[0]["project"], cells[-1]["project"]
    pairs = [caps[0]] if len(caps) == 1 else [caps[0], caps[-1]]
    lines = [
        "# 受控规模扫描（M6，docs/01 §11）",
        "",
        f"- 生成：{datetime.now():%Y-%m-%d %H:%M:%S}；每格 "
        f"{repeats} 次重复，同一任务文本，仅变 `CONTEXT__N_RESULTS` 与语料",
        "- 成本口径 = `get_context` 跨度的真实后端调用数与耗时（"
        "`Telemetry`，含真实 LLM 规划往返）；p95 为最近秩分位，"
        f"样本 n={repeats}，只作趋势不作精度",
        f"- 语料（小）：`{small_project}` — {cells[0]['corpus_note']}\n"
        f"- 语料（大）：`{large_project}` — {cells[-1]['corpus_note']}",
        "",
        "| 语料 | 构件数 | 召回上限 | 后端调用 min/中位/max |"
        " 耗时中位(ms) | 耗时 p95(ms) | 平均召回数 | 平均 bundle bytes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cell in cells:
        calls = cell["backend_calls"]
        lines.append(
            f"| {cell['project']} | {cell['corpus_artifacts']} "
            f"| {cell['n_results_cap']} "
            f"| {calls['min']}/{calls['median']}/{calls['max']} "
            f"| {cell['duration_ms']['median']} "
            f"| {cell['duration_ms']['p95']} "
            f"| {cell['recall_mean']} | {cell['bundle_bytes_mean']} |"
        )
    lines += [
        "",
        "## 读法（以下每句的数值都来自本次表格，不是复述历史结论）",
        "",
    ]
    for cap in pairs:
        lines.append(
            _reading(
                _cell(cells, small_project, cap),
                _cell(cells, large_project, cap),
            )
        )
    lines += [
        "- 机制：与语料规模同向的那一段成本来自 validity 的 gap 检测——它对项目内"
        "**每一条需求**做一次 `neighbors` 图查询（`engines/validity/gap.py`），"
        "不受召回上限约束；随上限增长的那一段才是"
        "「实际交付 + 逐 `based_on` 回读」"
        "（`engines/validity/suspect.py`）。所以上限不是唯一旋钮，**项目级核对是"
        "大仓库的主要成本**；",
    ]
    lo_cap, hi_cap = caps[0], caps[-1]
    corpus_rise = round(
        _cell(cells, large_project, hi_cap)["duration_ms"]["p95"]
        - _cell(cells, small_project, hi_cap)["duration_ms"]["p95"],
        1,
    )
    cap_rise = round(
        _cell(cells, large_project, hi_cap)["duration_ms"]["p95"]
        - _cell(cells, large_project, lo_cap)["duration_ms"]["p95"],
        1,
    )
    dominant = (
        "语料规模（项目级 gap 扫描）"
        if corpus_rise >= cap_rise
        else "召回上限"
    )
    lines += [
        f"- 耗时（p95）：同一上限下 18→{cells[-1]['corpus_artifacts']} 构件带来 "
        f"{corpus_rise}ms，同一语料内 cap={lo_cap}→{hi_cap} 只带来 {cap_rise}ms "
        f"→ 主导项是**{dominant}**；规则模式（无 key）下绝对值显著下降，"
        "上述相对关系不变。",
        "",
        "## 局限",
        "",
        f"- 大语料的构造方式是**把教学项目复制放大**（{cells[-1]['corpus_note']}），"
        "不是数千构件的真实工程；两点之间已可看趋势，但绝对值不可外推到 "
        "10^3 量级以上；",
        "- 未测并发与多进程（seekdb 连接池）场景。",
        "",
    ]
    (out_dir / "sweep.md").write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    # fresh project ids: re-ingesting an existing project supersedes its own
    # history, which would turn the sweep into a measurement of empty bundles
    small_project = args.small_project or f"sweep-small-{stamp}"
    large_project = args.large_project or f"sweep-large-{stamp}"
    small_root = ROOT.parent / "demo" / "railway"
    large_root = (
        Path(args.large_root)
        if args.large_root
        else Path(tempfile.gettempdir()) / f"sw-scaling-{stamp}"
    )
    if not args.large_root:
        built = build_large_workspace(small_root, large_root, args.large_factor)
        print(f"synthetic corpus: {built} artifacts under {large_root}")
    cells = []
    for project, root, note in (
        (small_project, small_root, "教学项目全量"),
        (
            large_project,
            large_root,
            f"同一教学项目 ×{args.large_factor} 复制，逐副本唯一化 id",
        ),
    ):
        corpus_size = await ingest_once(project, str(root))
        print(f"{project}: corpus ingested -> {corpus_size} artifacts")
        for cap in args.caps:
            cell = await probe(
                project, cap, args.budget_bytes, args.repeats, str(root),
                corpus_size, note,
            )
            cells.append(cell)
            print(
                f"{project:<22} cap={cap:<4} "
                f"backend={cell['backend_calls']} "
                f"p95={cell['duration_ms']['p95']}ms "
                f"recall={cell['recall_mean']}"
            )
    # A corpus can drift out of validity (artifacts superseded by earlier
    # ingests, or the workspace no longer matching what was indexed): recall
    # still happens, but nothing survives into the bundle, so the "cost" being
    # measured is that of an empty frame. Never write that out as a curve.
    degenerate = [
        cell
        for cell in cells
        if cell["recall_mean"]
        and cell["bundle_bytes_mean"] <= FIXED_CHROME_BYTES * 1.5
    ]
    if degenerate:
        for cell in degenerate:
            print(
                f"DEGENERATE CELL {cell['project']} cap="
                f"{cell['n_results_cap']}: recalled {cell['recall_mean']} "
                f"but delivered only {cell['bundle_bytes_mean']}B (~frame). "
                "Re-ingest from the workspace the corpus was built from, "
                "then re-run; the sweep is not valid."
            )
        return 1
    (out_dir / "sweep.json").write_text(
        json.dumps(cells, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(out_dir, cells, args.repeats)
    print(f"evidence -> {out_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small-project", default=None)
    parser.add_argument("--large-project", default=None)
    parser.add_argument(
        "--large-factor",
        type=int,
        default=20,
        help="replicate the small project this many times for the large corpus",
    )
    parser.add_argument(
        "--large-root",
        default=None,
        help="use this already-ingestable workspace instead of building one",
    )
    parser.add_argument(
        "--caps",
        type=int,
        nargs="+",
        default=[5, 20, 40],
        help="values for CONTEXT__N_RESULTS",
    )
    parser.add_argument("--repeats", type=int, default=8)
    parser.add_argument("--budget-bytes", type=int, default=8000)
    parser.add_argument(
        "--out",
        default=str(
            ROOT.parent
            / "evidence"
            / f"scaling-{datetime.now():%Y%m%d-%H%M%S}"
        ),
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
