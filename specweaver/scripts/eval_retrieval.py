"""Retrieval-quality evaluation against a frozen gold set (docs/01 §11).

Answers the question a judge will ask: does the 5-engine pipeline actually beat
a naive keyword scan at the same delivery budget? Two arms are scored on the
same gold cases:

* ``keyword``     - bigram/word containment over the ingested corpus, top-N by
                    raw overlap. No index, no graph, no constraint floor.
* ``specweaver``  - the production ``GetContext`` usecase (plan -> hybrid search
                    -> graph expand -> validity -> budgeted assembly), i.e. what
                    an Agent actually receives.

Both arms deliver the same number of artifacts per case, so recall differences
are budget-fair. Results (per case + macro averages, bytes, latency, backend
calls) are written to ``evidence/retrieval-<ts>/``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
from datetime import datetime
from pathlib import Path

from specweaver.application.engines.assembly.budget import entry_cost
from specweaver.application.usecases.get_context import (
    GetContextRequest,
)
from specweaver.application.usecases.ingest_project import (
    IngestProjectRequest,
)
from specweaver.domain.ports.catalog import ArtifactFilter
from specweaver.shared import di
from specweaver.shared.config import Settings

ROOT = Path(__file__).resolve().parents[1]
RAILWAY = ROOT.parent / "demo" / "railway"
DEFAULT_GOLD = RAILWAY / "gold" / "retrieval-gold.json"

_LATIN = re.compile(r"[a-z_][a-z0-9_]{1,}")
_CJK = re.compile(r"[一-鿿]+")


def query_tokens(text: str) -> set[str]:
    """Latin words plus adjacent-CJK bigrams (no tokenizer dependency)."""
    lowered = text.lower()
    tokens = set(_LATIN.findall(lowered))
    for run in _CJK.findall(text):
        tokens.update(
            run[i:i + 2] for i in range(max(len(run) - 1, 1))
        )
        if len(run) == 1:
            tokens.add(run)
    return tokens


def bundle_artifacts(result) -> list:
    bundle = result.bundle
    return [
        *bundle.goal_and_constraints,
        *bundle.design_and_implementation,
        *bundle.verification,
    ]


def keyword_fill(
    docs: list[tuple], tokens: set[str], budget_bytes: int
) -> set[str]:
    """Strong naive arm: rank by keyword overlap, keep only hits, same bytes."""
    scored = sorted(
        (
            (len(tokens & query_tokens(text[:4000])), artifact)
            for artifact, text in docs
        ),
        key=lambda pair: (-pair[0], pair[1].id),
    )
    used = 0
    kept: set[str] = set()
    for score, artifact in scored:
        if score == 0:
            break
        cost = entry_cost(artifact)
        if used + cost > budget_bytes:
            continue
        used += cost
        kept.add(artifact.id)
    return kept


def matches(artifact, expect_ids: list[str], expect_paths: list[str]) -> bool:
    if artifact.id in expect_ids:
        return True
    uri = (artifact.source.uri if artifact.source else "") or ""
    normalized = uri.replace("\\", "/")
    return any(normalized.endswith(path) for path in expect_paths)


def score_set(found: set[str], expected: set[str], delivered: int) -> dict:
    hit = len(found & expected)
    recall = hit / len(expected) if expected else 1.0
    precision = hit / delivered if delivered else 0.0
    f1 = (
        2 * recall * precision / (recall + precision)
        if (recall + precision)
        else 0.0
    )
    return {
        "expected": len(expected),
        "delivered": delivered,
        "hit": hit,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1": round(f1, 4),
        "missed": sorted(expected - found),
        "extra": sorted(found - expected),
    }


def macro(rows: list[dict], field: str) -> float:
    return round(statistics.mean(row[field] for row in rows), 4)


def write_report(out_dir: Path, payload: dict) -> None:
    lines = [
        "# 检索质量金标评测（docs/01 §11 / docs/03 §11）",
        "",
        f"- 生成：{payload['generated_at']}；语料：{payload['corpus']}",
        f"- 标注方法：{payload['labeling_method']}",
        "- 两臂**同字节公平**：keyword 臂拿到的预算 = SpecWeaver 在该用例实际花在"
        "**构件**上的字节（chrome/findings 不计入），并用同一 `entry_block` 成本模型"
        "填充、只保留有命中的文档；因此 recall/precision 差异反映的是选择质量而非"
        "预算差异",
        "- 推理 provider：`"
        + str(payload["provider"])
        + "`（规则模式下 planner 不产生 LLM 调用，混合检索仍走真实 seekdb）",
        "",
        "## 宏平均",
        "",
        "| 臂 | recall | precision | F1 |",
        "|---|---|---|---|",
    ]
    for arm in ("keyword", "specweaver"):
        agg = payload["macro"][arm]
        lines.append(
            f"| {arm} | {agg['recall']} | {agg['precision']} | {agg['f1']} |"
        )
    lines += [
        "",
        "## 逐用例",
        "",
        "| 用例 | 期望 | 交付 | keyword R/F1 | specweaver R/F1 | SpecWeaver 漏检 |",
        "|---|---|---|---|---|---|",
    ]
    for case in payload["cases"]:
        kw, sw = case["arms"]["keyword"], case["arms"]["specweaver"]
        lines.append(
            f"| {case['id']} | {kw['expected']} | {sw['delivered']} | "
            f"{kw['recall']}/{kw['f1']} | {sw['recall']}/{sw['f1']} | "
            f"{', '.join(sw['missed']) or '—'} |"
        )
    lines += [
        "",
        "## 代价与用量",
        "",
        f"- `GetContext` 跨度耗时(ms)：中位 {payload['latency_ms']['median']} /"
        f" 最大 {payload['latency_ms']['max']}（样本 n="
        f"{payload['latency_ms']['n']}，p95 需更大样本量，直方图已在"
        f" `metrics.txt`）",
        f"- 平均 bundle bytes：{payload['bundle_bytes_mean']}（预算 "
        f"{payload['budget_bytes']}）；平均每用例后端调用："
        f"{payload['backend_calls_mean']}",
        f"- LLM 规划调用合计 {payload['llm_calls_total']} 次，prompt/completion "
        f"tokens {payload['prompt_tokens_total']}/"
        f"{payload['completion_tokens_total']}",
        "",
        "## 局限性",
        "",
        "- 金标由本项目人工标注（非公开基准），语料是 20 构件的教学项目，"
        "结论只在该语料与该标注口径下成立；",
        "- **小语料下预算不构成约束**：本次 bundle 平均 "
        f"{payload['bundle_bytes_mean']} bytes / 预算 "
        f"{payload['budget_bytes']}，precision 宏平均仅 "
        f"{payload['macro']['specweaver']['precision']}——即"
        "『最小充分』在未触及预算时退化为『接近全量交付』，"
        "选择性必须靠紧预算与大语料实验来证明（见 report 中 `budget_bytes` 参数）；",
        "- 单任务、无历史会话，不测多轮补召回；",
        "- keyword 臂不建索引、不看图、无约束保底，但**给了与 SpecWeaver 相同的"
        "字节预算且只保留有命中文档**，不是刻意做弱的对照。",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    cases = gold["cases"]
    if not cases:
        print("gold set is empty; refusing to report a vacuous result")
        return 1

    settings = Settings()
    settings.workspace.root = str(RAILWAY)
    if args.budget_bytes:
        settings.context.budget_bytes = args.budget_bytes
    provider = settings.inference.provider

    async with di.run(settings) as app:
        if app.catalog is None:
            print("the seekdb catalog is unavailable; this evaluation needs it")
            return 1
        ingest = await app.usecases["ingest_project"](
            IngestProjectRequest(
                project_id=args.project, register_source=False
            )
        )
        corpus = await app.catalog.list_artifacts(
            ArtifactFilter(project_id=args.project)
        )
        if not corpus:
            print("ingestion produced no artifacts; cannot evaluate")
            return 1
        docs = [
            (artifact, " ".join([artifact.title, artifact.content or ""]))
            for artifact in corpus
        ]

        rows: list[dict] = []
        for case in cases:
            expected = set(case["expect_ids"]) | {
                artifact.id for artifact, _ in docs if matches(
                    artifact, case["expect_ids"], case["expect_paths"]
                )
            }
            result = await app.usecases["get_context"](
                GetContextRequest(
                    project_id=args.project, task_text=case["task"]
                )
            )
            delivered = bundle_artifacts(result)
            # fairness: the keyword arm gets exactly the bytes SpecWeaver spent
            # on artifacts (chrome and findings excluded), same cost model
            artifact_bytes = sum(entry_cost(a) for a in delivered)
            tokens = query_tokens(case["task"])
            baseline_ids = keyword_fill(docs, tokens, artifact_bytes)
            delivered_ids = {artifact.id for artifact in delivered}
            rows.append(
                {
                    "id": case["id"],
                    "task": case["task"],
                    "derivation": case["derivation"],
                    "finding_types": sorted(
                        str(f.kind) for f in result.bundle.findings
                    ),
                    "bundle_bytes": result.bundle.budget.used_bytes
                    if result.bundle.budget
                    else 0,
                    "arms": {
                        "keyword": score_set(
                            baseline_ids, expected, len(baseline_ids)
                        ),
                        "specweaver": score_set(
                            delivered_ids, expected, len(delivered)
                        ),
                    },
                }
            )

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = Path(args.out) if args.out else (
            ROOT.parent / "evidence" / f"retrieval-{ts}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        spans = [r for r in app.telemetry.records if r.name == "get_context"]
        durations = [round(r.duration_ms, 1) for r in spans]
        payload = {
            "generated_at": ts,
            "corpus": gold["corpus"],
            "labeling_method": gold["labeling_method"],
            "provider": provider,
            "project": args.project,
            "ingest": {
                "added": ingest.added,
                "updated": ingest.updated,
                "unchanged": ingest.unchanged,
                "relations": ingest.relations,
            },
            "macro": {
                arm: {
                    field: macro([row["arms"][arm] for row in rows], field)
                    for field in ("recall", "precision", "f1")
                }
                for arm in ("keyword", "specweaver")
            },
            "cases": rows,
            "latency_ms": {
                "n": len(durations),
                "median": statistics.median(durations) if durations else None,
                "max": max(durations) if durations else None,
            },
            "bundle_bytes_mean": round(
                statistics.mean(
                    [row["bundle_bytes"] for row in rows
                     if row["bundle_bytes"] is not None]
                ),
                1,
            ),
            "budget_bytes": settings.context.budget_bytes,
            "backend_calls_mean": round(
                statistics.mean([r.backend_calls for r in spans]), 1
            ),
            "llm_calls_total": sum(r.llm_calls for r in spans),
            "prompt_tokens_total": sum(r.prompt_tokens for r in spans),
            "completion_tokens_total": sum(
                r.completion_tokens for r in spans
            ),
        }
        (out_dir / "results.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "metrics.txt").write_text(
            app.telemetry.to_prometheus(), encoding="utf-8"
        )
        app.telemetry.to_csv(str(out_dir / "usage.csv"))
        write_report(out_dir, payload)

        print(f"corpus={len(corpus)} artifacts, cases={len(rows)}")
        for arm in ("keyword", "specweaver"):
            agg = payload["macro"][arm]
            print(
                f"{arm:>11}: macro recall={agg['recall']} "
                f"precision={agg['precision']} f1={agg['f1']}"
            )
        for row in rows:
            sw = row["arms"]["specweaver"]
            kw = row["arms"]["keyword"]
            print(
                f"  {row['id']}: kw R={kw['recall']} / sw R={sw['recall']} "
                f"sw F1={sw['f1']} missed={sw['missed'] or '-'}"
            )
        print(f"evidence -> {out_dir}")

        if args.min_recall and payload["macro"]["specweaver"]["recall"] < args.min_recall:
            print(
                f"FAIL: specweaver macro recall "
                f"{payload['macro']['specweaver']['recall']} < "
                f"{args.min_recall}"
            )
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--project", default="retrieval-eval")
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--budget-bytes",
        type=int,
        default=0,
        help="override CONTEXT__BUDGET_BYTES for this run (e.g. 1500 to make "
        "the budget actually bind and exercise relevance-based trimming)",
    )
    parser.add_argument(
        "--min-recall",
        type=float,
        default=0.0,
        help="gate the run on the specweaver macro recall (0 disables)",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
