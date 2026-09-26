"""Railway teaching demo driven end-to-end by SpecWeaver (real backends).

Copies demo/railway into a scratch git repo, then replays the docs/01 §10.2
flow: K0 ingest + rule memory -> K2 get_context -> K3 scripted edit ->
K4/K5 complete_task -> handoff -> K6 resume after "interruption" ->
linked second change -> K7 evidence chain into <repo>/evidence/<project>/.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from specweaver.application.engines.assembly import render_json
from specweaver.application.usecases.complete_task import CompleteTaskRequest
from specweaver.application.usecases.create_handoff import CreateHandoffRequest
from specweaver.application.usecases.get_context import GetContextRequest
from specweaver.application.usecases.ingest_project import IngestProjectRequest
from specweaver.application.usecases.resume_task import ResumeTaskRequest
from specweaver.domain.enums import ArtifactType
from specweaver.domain.ports.catalog import ArtifactFilter
from specweaver.domain.ports.memory import MemoryEntry
from specweaver.shared import di
from specweaver.shared.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_SRC = REPO_ROOT / "demo" / "railway"

TASK_TEXT = "为列车按站调整发车时间并重算后续各站时刻，检查占用冲突并阻止发布"

SCHEDULE_ADJUST = '''

def adjust_departure(train: Train, new_start: str) -> Train:
    """按站调整发车时间：以新始发时刻平移整条时刻表（REQ-1）。"""
    return Train(
        train_id=train.train_id, start=new_start, legs=dict(train.legs)
    )
'''

TEST_ADJUST = '''"""发车时间调整回归测试（REQ-1 新行为）。"""

from schedule import Train, adjust_departure, arrival_times


def make_train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_adjust_departure_shifts_whole_timetable() -> None:
    adjusted = adjust_departure(make_train(), "08:30")
    assert arrival_times(adjusted) == {
        "A": "08:30", "B": "08:40", "C": "08:55",
    }
'''

API_ENTRY = '''

def submit_adjust_departure(
    train: Train, new_start: str
) -> dict[str, str]:
    """提交新始发时刻并返回调整后的时刻表（REQ-4 入口）。"""
    from schedule import adjust_departure

    return arrival_times(adjust_departure(train, new_start))
'''

SCHEDULE_AUDIT = '''

ADJUST_AUDIT: list[tuple[str, str, str]] = []


def adjust_departure_logged(train: Train, new_start: str) -> Train:
    """调整发车时间并记录审计日志（REQ-6 增量）。"""
    adjusted = adjust_departure(train, new_start)
    ADJUST_AUDIT.append((train.train_id, train.start, new_start))
    return adjusted
'''

SPEC_V2 = '''---
id: REQ-06
type: requirement
module: schedule
version: 2.0.0
status: active
supersedes: REQ-01
title: 按站调整发车时间（升版：含审计）
---

# 按站调整发车时间（升版）

本需求为 REQ-1 的升版：

- 调度员应能按站点修改发车时间并自动重算后续各站时刻
- 每次调整必须记录审计日志
'''

TEST_AUDIT = '''"""调整联动回归测试（REQ-6 审计 + REQ-2 占用复核）。"""

from occupancy import Occupation
from publish import can_publish
from schedule import ADJUST_AUDIT, Train, adjust_departure_logged


def make_train() -> Train:
    return Train(train_id="K1", start="08:00", legs={"A->B": 10, "B->C": 15})


def test_audit_log_records_adjustment() -> None:
    before = len(ADJUST_AUDIT)
    adjust_departure_logged(make_train(), "09:00")
    assert len(ADJUST_AUDIT) == before + 1


def test_adjusted_train_still_checked_for_occupancy() -> None:
    adjusted = adjust_departure_logged(make_train(), "08:05")
    busy = [Occupation("K1", 486, 494)]
    ok, _ = can_publish(adjusted, busy)
    assert not ok
'''


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return proc.stdout.strip()


def findings_count(ctx) -> dict[str, int]:
    out: dict[str, int] = {}
    for finding in ctx.bundle.findings:
        out[finding.kind.value] = out.get(finding.kind.value, 0) + 1
    return out


async def run(out_root: Path, keep_temp: bool) -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    project = f"railway-{stamp}"
    evidence = out_root / project
    evidence.mkdir(parents=True, exist_ok=True)
    actions: list[dict] = []

    temp = Path(tempfile.mkdtemp(prefix="railway-demo-"))
    workdir = temp / "railway"
    shutil.copytree(
        DEMO_SRC,
        workdir,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    git(workdir, "init", "-q")
    git(workdir, "config", "user.name", "specweaver-demo")
    git(workdir, "config", "user.email", "demo@specweaver.local")
    git(workdir, "add", "-A")
    git(workdir, "commit", "-q", "-m", "baseline: railway v1 assets")
    base1 = git(workdir, "rev-parse", "HEAD")

    settings = Settings()
    settings.workspace.root = str(workdir)
    pytest_cmd = f'"{sys.executable}" -m pytest -q'
    usecases = {}

    def write(name: str, text: str) -> None:
        (evidence / name).write_text(text, encoding="utf-8")

    def dump(name: str, payload) -> None:
        write(name, json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        async with di.run(settings) as app:
            usecases = app.usecases
            scope = await app.ensure_scope(project, "")
            actions.append(
                {"op": "ensure_scope", "project": project, "scope_id": scope}
            )

            # K0: ingest into seekdb + write constitution rules to memory
            ing = await usecases["ingest_project"](
                IngestProjectRequest(project_id=project, scope_id=scope)
            )
            dump("01-ingest.json", ing.model_dump(mode="json"))
            rules = await app.catalog.list_artifacts(
                ArtifactFilter(
                    project_id=project, types=[ArtifactType.rule]
                )
            )
            for rule in rules:
                entry = await app.memory.remember(
                    MemoryEntry(
                        scope_id=scope,
                        kind="constraint",
                        content=f"[{rule.id}] {rule.content.strip()}",
                        tags=["constraint", project],
                    )
                )
                actions.append(
                    {"op": "remember_rule", "id": rule.id, "entry_id": entry.id}
                )

            # K1/K2: ask for context
            ctx2 = await usecases["get_context"](
                GetContextRequest(
                    project_id=project, task_text=TASK_TEXT, base_ref=base1
                )
            )
            dump(
                "02-context.json",
                {
                    "bundle": json.loads(render_json(ctx2.bundle)),
                    "excluded": [
                        {
                            "id": e.artifact.id,
                            "reasons": e.reasons,
                        }
                        for e in ctx2.excluded
                    ],
                },
            )
            write("02-context.md", ctx2.markdown)
            print(
                f"K2 findings: {findings_count(ctx2)} "
                f"cited={len(ctx2.bundle.citations)} "
                f"used={ctx2.bundle.budget.used_bytes}"
            )

            # K3: scripted agent edits (schedule/api + new regression test)
            (workdir / "src" / "schedule.py").write_text(
                (workdir / "src" / "schedule.py").read_text(encoding="utf-8")
                + SCHEDULE_ADJUST,
                encoding="utf-8",
            )
            (workdir / "src" / "api.py").write_text(
                (workdir / "src" / "api.py").read_text(encoding="utf-8")
                + API_ENTRY,
                encoding="utf-8",
            )
            (workdir / "tests" / "test_adjust.py").write_text(
                TEST_ADJUST, encoding="utf-8"
            )
            git(workdir, "add", "-A")
            git(workdir, "commit", "-q", "-m", "feat: adjust departure by stop")
            head2 = git(workdir, "rev-parse", "HEAD")

            # K4/K5: tool runs the tests, reconciles, records evidence
            done2 = await usecases["complete_task"](
                CompleteTaskRequest(
                    project_id=project,
                    task_id=f"{project}-adjust",
                    base_ref=base1,
                    scope_id=scope,
                    test_command=pytest_cmd,
                )
            )
            dump("03-complete-adjust.json", done2.model_dump(mode="json"))
            write(
                "changes-1.diff", git(workdir, "diff", base1, head2) + "\n"
            )

            # K5b: handoff snapshot for the simulated interruption
            hand = await usecases["create_handoff"](
                CreateHandoffRequest(
                    project_id=project,
                    scope_id=scope,
                    objective=TASK_TEXT,
                    state=[
                        "schedule/api 调整能力已实现并通过全量回归",
                        "变更集与测试证据已回写 seekdb",
                    ],
                    next_steps=["联动 occupancy/publish 复核并升版规格"],
                    omissions=["审计日志需求 REQ-6 尚未落地"],
                )
            )
            dump("04-handoff.json", hand.model_dump(mode="json"))
            actions.append(
                {"op": "commit_handoff", "rev": hand.handoff_rev}
            )

            # K6: new session resumes from the handoff rev
            resumed = await usecases["resume_task"](
                ResumeTaskRequest(
                    project_id=project,
                    scope_id=scope,
                    handoff_rev=hand.handoff_rev,
                )
            )
            dump(
                "05-resume.json",
                {
                    "objective": resumed.objective,
                    "progress": resumed.progress,
                    "next_steps": resumed.next_steps,
                    "handoff_resumed": resumed.handoff_resumed,
                    "mismatches": [
                        m.model_dump(mode="json")
                        for m in resumed.mismatches
                    ],
                },
            )
            print(
                f"K6 resumed={resumed.handoff_resumed} "
                f"mismatches={len(resumed.mismatches)}"
            )

            # K6b: linked change (audit log + occupancy recheck) + spec v2
            (workdir / "src" / "schedule.py").write_text(
                (workdir / "src" / "schedule.py").read_text(encoding="utf-8")
                + SCHEDULE_AUDIT,
                encoding="utf-8",
            )
            (workdir / "specs" / "requirement-schedule-v2.md").write_text(
                SPEC_V2, encoding="utf-8"
            )
            (workdir / "tests" / "test_audit.py").write_text(
                TEST_AUDIT, encoding="utf-8"
            )
            git(workdir, "add", "-A")
            git(
                workdir, "commit", "-q",
                "-m", "feat: audit log + spec v2 supersedes REQ-1",
            )
            head3 = git(workdir, "rev-parse", "HEAD")
            done3 = await usecases["complete_task"](
                CompleteTaskRequest(
                    project_id=project,
                    task_id=f"{project}-audit",
                    base_ref=head2,
                    scope_id=scope,
                    test_command=pytest_cmd,
                )
            )
            dump("06-complete-audit.json", done3.model_dump(mode="json"))
            write(
                "changes-2.diff", git(workdir, "diff", head2, head3) + "\n"
            )

            # K7: final context shows superseded exclusion + suspect shots
            ctx7 = await usecases["get_context"](
                GetContextRequest(
                    project_id=project, task_text=TASK_TEXT, base_ref=head3
                )
            )
            dump(
                "07-context-final.json",
                {
                    "bundle": json.loads(render_json(ctx7.bundle)),
                    "excluded": [
                        {"id": e.artifact.id, "reasons": e.reasons}
                        for e in ctx7.excluded
                    ],
                },
            )
            write("07-context-final.md", ctx7.markdown)
            print(
                f"K7 findings: {findings_count(ctx7)} "
                f"excluded={len(ctx7.excluded)}"
            )

            write("powercontext-actions.jsonl",
                  "\n".join(json.dumps(a, ensure_ascii=False)
                            for a in actions) + "\n")
            app.telemetry.to_csv(str(evidence / "usage.csv"))
            ok = done2.success and done3.success
            write(
                "summary.md",
                "\n".join(
                    [
                        f"# railway demo {project}",
                        "",
                        f"- 摄入：+{ing.added} artifacts /"
                        f" {ing.relations} relations（增量 0 变更复跑）",
                        f"- K2 findings：{findings_count(ctx2)}",
                        f"- 调整步骤：tests {done2.test_passed}/"
                        f"{done2.test_total} passed，"
                        f"change_set={done2.change_set_id}",
                        f"- 联动步骤：tests {done3.test_passed}/"
                        f"{done3.test_total} passed，"
                        f"change_set={done3.change_set_id}",
                        f"- handoff rev：{hand.handoff_rev}；resume "
                        f"mismatches={len(resumed.mismatches)}",
                        f"- K7 findings：{findings_count(ctx7)}；"
                        f"excluded={len(ctx7.excluded)}"
                        "（REQ-1 已被 REQ-6 取代）",
                        f"- 用量：见 usage.csv；结果 ok={ok}",
                        "",
                    ]
                ),
            )
            print(f"evidence -> {evidence}")
            return 0 if ok else 1
    finally:
        if not keep_temp:
            shutil.rmtree(temp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default=str(REPO_ROOT / "evidence"),
        help="evidence output root (default: repo-root evidence/)",
    )
    parser.add_argument(
        "--keep-temp", action="store_true",
        help="keep the scratch git repo for inspection",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(Path(args.out), args.keep_temp)))


if __name__ == "__main__":
    main()
