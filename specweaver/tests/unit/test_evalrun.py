"""EvalRun schema, budget builder, and the two evidence collectors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specweaver.evaluation.artifact import (
    AgentRef,
    EvalMeta,
    UsageBlock,
    build_evalrun,
    collect_demo,
    collect_off_on,
    detect_layout,
    load_evalrun,
)
from specweaver.evaluation.taskpack import load_pack
from specweaver.shared.errors import InvalidRequest

AGENT = AgentRef(name="test-agent", version="9.9", model="test-model")


def _demo_tree(root: Path) -> None:
    (root / "01-ingest.json").write_text(
        json.dumps(
            {
                "project_id": "railway-x",
                "added": 4,
                "updated": 0,
                "unchanged": 0,
                "skipped": 0,
                "relations": 5,
                "changed_ids": ["REQ-1"],
                "duplicate_ids": [],
                "deprecated": 0,
            }
        ),
        encoding="utf-8",
    )
    bundle = {
        "task": {"title": "按站调整发车时间"},
        "citations": [
            {
                "artifact_id": "REQ-1",
                "version": "1.0.0",
                "source": {"uri": "specs/requirement-schedule.md",
                           "locator": "L3"},
                "updated_at": "2026-09-27T00:00:00",
            }
        ],
        "findings": [{"kind": "gap"}, {"kind": "conflict"}],
        "budget": {"max_bytes": 8000, "used_bytes": 6617, "truncated": False},
    }
    for name in ("02-context.json", "07-context-final.json"):
        (root / name).write_text(
            json.dumps({"bundle": bundle, "excluded": []}), encoding="utf-8"
        )
        (root / name.replace(".json", ".md")).write_text("# bundle\n",
                                                         encoding="utf-8")
    complete = {
        "task_id": "adjust",
        "success": True,
        "test_total": 11,
        "test_passed": 11,
        "test_failed": 0,
        "files_changed": ["src/api.py"],
        "change_set_id": "cs-1",
        "test_run_id": "tr-1",
    }
    (root / "03-complete-adjust.json").write_text(
        json.dumps(complete), encoding="utf-8"
    )
    (root / "04-handoff.json").write_text(
        json.dumps({"handoff_rev": "hw-42", "objective": "continue"}),
        encoding="utf-8",
    )
    (root / "05-resume.json").write_text(
        json.dumps({"handoff_resumed": True, "mismatches": []}),
        encoding="utf-8",
    )
    (root / "powercontext-actions.jsonl").write_text(
        '\n'.join(
            [
                json.dumps({"op": "ensure_scope", "scope_id": "scp-1"}),
                json.dumps({"op": "remember_rule", "id": "RULE-1",
                            "entry_id": "mem_ent_1"}),
            ]
        ),
        encoding="utf-8",
    )
    (root / "changes-1.diff").write_text("diff --git a b\n", encoding="utf-8")
    rows = [
        "name,duration_ms,llm_calls,prompt_tokens,completion_tokens,"
        "backend_calls,status,error,metrics",
        'ingest_project,100.0,0,0,0,3,ok,,{}',
        'get_context,200.0,1,50,40,5,ok,,"{""recall"": 2, ""findings"": 2}"',
    ]
    (root / "usage.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _off_on_tree(root: Path) -> None:
    records = [
        {
            "arm": "on", "run": 0, "project_id": "offon-on-0-x", "rc": 0,
            "sw_calls": ["sw_ingest_project", "sw_get_context"],
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "cache_read_input_tokens": 7},
            "duration_ms": 12000.0, "num_turns": 9, "result_text": "done",
            "changed": True, "pytest_rc": 0, "summary": "13 passed",
            "success": True,
        },
        {
            "arm": "off", "run": 0, "project_id": "offon-off-0-x", "rc": 0,
            "sw_calls": [], "usage": {"input_tokens": 300}, "duration_ms": 9000.0,
            "num_turns": 12, "result_text": "done", "changed": True,
            "pytest_rc": 1, "summary": "2 failed", "success": False,
        },
    ]
    (root / "summary.json").write_text(
        json.dumps(records, ensure_ascii=False), encoding="utf-8"
    )
    on_dir = root / "on-0"
    on_dir.mkdir()
    (on_dir / "agent.diff").write_text("diff --git a b\n", encoding="utf-8")
    (on_dir / "judge.txt").write_text("13 passed\n", encoding="utf-8")


def test_layout_detection_and_failure(tmp_path: Path) -> None:
    with pytest.raises(InvalidRequest, match="unrecognized evidence layout"):
        detect_layout(tmp_path)


def test_collect_demo_maps_every_block(tmp_path: Path) -> None:
    _demo_tree(tmp_path)
    run = collect_demo(tmp_path, agent=AGENT, sw_version="abc1234")
    assert run.meta.source == "railway-demo"
    assert run.meta.sw_version == "abc1234"

    assert run.usage.llm_calls == 1
    assert run.usage.prompt_tokens == 50
    assert run.usage.completion_tokens == 40
    assert run.usage.backend_calls == 8
    assert run.usage.spans == 2

    assert len(run.context_bundles) == 2
    first = run.context_bundles[0]
    assert first.task == "按站调整发车时间"
    assert first.bundle_ref == "02-context.md"
    assert first.bundle_bytes == 6617
    assert first.findings == 2
    assert first.citations[0].artifact_id == "REQ-1"
    assert first.citations[0].source_uri == "specs/requirement-schedule.md"
    assert first.citations[0].locator == "L3"

    assert run.test_evidence[0].total == 11
    assert run.test_evidence[0].passed == 11
    assert run.code_diff.diff_refs == ["changes-1.diff"]
    assert "src/api.py" in run.code_diff.files_changed

    actions = [op.action for op in run.memory_ops]
    assert actions[:2] == ["handoff", "resume"]
    assert run.memory_ops[0].ref == "hw-42"
    assert "ensure_scope" in actions and "remember_rule" in actions
    assert run.memory_ops[-1].ref == "mem_ent_1"

    assert run.outcome.success is True
    assert run.outcome.source == "complete_task.success"
    assert set(run.sources) >= {
        "usage.csv", "01-ingest.json", "02-context.json",
        "03-complete-adjust.json", "powercontext-actions.jsonl",
        "changes-1.diff",
    }


def test_collect_off_on_one_evalrun_per_record(tmp_path: Path) -> None:
    _off_on_tree(tmp_path)
    runs = collect_off_on(tmp_path, agent=AGENT, sw_version="abc1234")
    assert [r.meta.arm for r in runs] == ["on", "off"]

    on = runs[0]
    assert on.usage.prompt_tokens == 100
    assert on.usage.completion_tokens == 50
    assert on.usage.agent_usage_raw["cache_read_input_tokens"] == 7
    assert on.code_diff.diff_refs == ["on-0/agent.diff"]
    assert on.test_evidence[0].exit_code == 0
    assert on.outcome.success is True
    assert on.outcome.source == "summary.success"
    assert any("transcript.jsonl" in note for note in on.outcome.notes)

    off = runs[1]
    assert off.usage.prompt_tokens == 300
    assert off.outcome.success is False
    assert off.test_evidence[0].summary == "2 failed"
    assert off.code_diff.diff_refs == []  # no agent.diff materialized


def test_budget_over_rules_and_taskpack_attach(tmp_path: Path) -> None:
    _demo_tree(tmp_path)
    pack = load_pack(Path(__file__).resolve().parents[2] / "taskpacks" /
                     "railway-basic.json")
    run = collect_demo(tmp_path, agent=AGENT, taskpack=pack)

    assert run.meta.taskpack_id == "railway-basic"
    assert run.meta.tier == "basic"
    assert run.budget.declared["max_tokens"] == 200000.0
    # demo usage.csv totals are tiny: nothing is over budget
    assert run.budget.over == []
    assert run.budget.actual["max_backend_calls"] == 8.0


def test_budget_over_flags_exceeded_keys(tmp_path: Path) -> None:
    tiny = dict(json.loads(
        (Path(__file__).resolve().parents[2] / "taskpacks" /
         "railway-basic.json").read_text(encoding="utf-8")
    ))
    tiny["budget"] = {"max_tokens": 100, "max_backend_calls": 5,
                      "time_limit_s": 900}
    pack = load_pack(_write(tmp_path, tiny, "tiny-pack.json"))

    meta = EvalMeta(source="run_eval", agent=AGENT)
    usage = UsageBlock(prompt_tokens=120, backend_calls=9, duration_ms=60_000.0)
    run = build_evalrun(meta, usage=usage, taskpack=pack)

    assert run.budget.over == ["max_tokens", "max_backend_calls"]
    assert run.budget.actual["time_limit_s"] == 60.0
    assert run.budget.actual["time_limit_s"] <= run.budget.declared["time_limit_s"]


def _write(root: Path, data: object, name: str) -> Path:
    target = root / name
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return target


def test_strict_schema_rejects_unknown_fields(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "meta": {"source": "run_eval", "agent": {"name": "x"}},
        "oops": True,
    }
    target = tmp_path / "evalrun.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InvalidRequest, match="oops"):
        load_evalrun(target)


def test_emit_round_trip(tmp_path: Path) -> None:
    _demo_tree(tmp_path)
    run = collect_demo(tmp_path, agent=AGENT, sw_version="abc1234")
    out = tmp_path / "evalrun.json"
    out.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    assert load_evalrun(out) == run


def test_collect_demo_rejects_bad_usage_row(tmp_path: Path) -> None:
    _demo_tree(tmp_path)
    csv_path = tmp_path / "usage.csv"
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    lines.insert(1, "get_context,xx-not-a-number,0,0,0,0,ok,,{}")
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(InvalidRequest, match="usage.csv.*bad row 2"):
        collect_demo(tmp_path, agent=AGENT)


def test_collect_demo_skips_non_object_action_lines(tmp_path: Path) -> None:
    _demo_tree(tmp_path)
    actions = tmp_path / "powercontext-actions.jsonl"
    actions.write_text(
        json.dumps({"op": "ensure_scope", "scope_id": "scp-1"}) + "\n"
        + "[1, 2]\n"  # malformed earlier write: skipped, never crashes
        + json.dumps({"op": "remember_rule", "id": "RULE-1",
                      "entry_id": "mem_ent_1"}) + "\n",
        encoding="utf-8",
    )
    run = collect_demo(tmp_path, agent=AGENT)
    assert [op.ref for op in run.memory_ops if op.action == "ensure_scope"] == [
        "scp-1"
    ]


def test_collect_off_on_rejects_malformed_records(tmp_path: Path) -> None:
    (tmp_path / "summary.json").write_text(
        json.dumps([{"arm": "sideways", "run": 0}]), encoding="utf-8"
    )
    with pytest.raises(InvalidRequest, match="record 0"):
        collect_off_on(tmp_path, agent=AGENT)

    (tmp_path / "summary.json").write_text(
        json.dumps([{"arm": "on"}]), encoding="utf-8"
    )
    with pytest.raises(InvalidRequest, match="integer run"):
        collect_off_on(tmp_path, agent=AGENT)
