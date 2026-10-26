"""Harness building blocks: invocation, config, parsing, checkout, judge."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from specweaver.evaluation.harness import (
    backend_probe,
    build_prompt,
    checkout_pack,
    hidden_suite_source,
    invocation_for,
    judge_workspace,
    mcp_config_for,
    parse_transcript,
    plan_workdir,
)
from specweaver.evaluation.taskpack import load_pack, materialize
from specweaver.shared.errors import InvalidRequest

PACK = {
    "id": "demo-basic",
    "tier": "basic",
    "repo": {"origin": "https://example.invalid/demo.git",
             "commit": "abc1234", "subdir": "src"},
    "agent": {"name": "claude-code", "version": "1.0", "model": "m"},
    "task": {
        "goal": "add the filter entry point",
        "contract": "src/api.py gains filter_books(books) -> list",
    },
    "acceptance": {"test_commands": ["python -m pytest -q"],
                   "forbidden_regressions": ["REQ-1"]},
}


def _pack(tmp_path: Path) -> object:
    target = tmp_path / "pack.json"
    target.write_text(json.dumps(PACK), encoding="utf-8")
    return load_pack(target)


def _plan(tmp_path: Path, pack) -> object:
    return materialize(pack, "run1", tmp_path / "work")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout.strip()


def test_prompt_carries_goal_contract_project_and_guard(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    prompt = build_prompt(pack, "demo-basic-r1", arm="off")
    assert "add the filter entry point" in prompt
    assert "filter_books(books)" in prompt  # contract inlined
    assert "demo-basic-r1" in prompt
    assert "REQ-1" in prompt  # regression guard surfaced
    assert "mcp__specweaver" not in prompt  # OFF arm: no tool hint

    on_prompt = build_prompt(pack, "demo-basic-r1", arm="on")
    assert "mcp__specweaver" in on_prompt


def test_invocation_arms_differ_only_by_mcp_config(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    plan = _plan(tmp_path, pack)
    cfg = tmp_path / "mcp.json"
    off_cmd, _ = invocation_for(pack, plan, arm="off", cfg_path=None)
    on_cmd, _ = invocation_for(pack, plan, arm="on", cfg_path=cfg)
    assert not any("--mcp-config" in part for part in off_cmd)
    assert "--mcp-config" in on_cmd and "--strict-mcp-config" in on_cmd
    assert str(cfg) in on_cmd
    with pytest.raises(InvalidRequest, match="MCP config"):
        invocation_for(pack, plan, arm="on", cfg_path=None)


def test_mcp_config_seams_point_at_this_run(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    plan = _plan(tmp_path, pack)
    config = mcp_config_for(plan, usage_out=tmp_path / "u.csv")
    server = config["mcpServers"]["specweaver"]
    assert server["command"] == sys.executable
    env = server["env"]
    assert env["WORKSPACE__ROOT"] == str(plan_workdir(plan))
    assert env["WORKSPACE__ROOT"].endswith("demo-basic-run1\\src") or \
        env["WORKSPACE__ROOT"].endswith("demo-basic-run1/src")
    assert env["PYTHONPATH"].endswith("src")
    assert env["SPECWEAVER_USAGE_OUT"] == str(tmp_path / "u.csv")


def test_parse_transcript_extracts_calls_and_usage() -> None:
    events = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "content": [
                {"type": "tool_use",
                 "name": "mcp__specweaver__sw_get_context"},
                {"type": "text", "text": "thinking"},
            ]},
        }),
        json.dumps({
            "type": "result",
            "num_turns": 7,
            "usage": {"input_tokens": 11, "output_tokens": 3},
            "result": "done",
        }),
        "not json at all",
    ]
    parsed = parse_transcript("\n".join(events))
    assert parsed["sw_calls"] == ["sw_get_context"]
    assert parsed["num_turns"] == 7
    assert parsed["usage"]["input_tokens"] == 11
    assert parsed["result_text"] == "done"


def test_backend_probe_reports_each_target() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    dead = socket.socket()
    dead.bind(("127.0.0.1", 0))
    dead_port = dead.getsockname()[1]
    dead.close()
    try:
        status = backend_probe(targets={
            "up": ("127.0.0.1", port),
            "down": ("127.0.0.1", dead_port),
        })
    finally:
        listener.close()
    assert status == {"up": True, "down": False}


def test_checkout_pack_pins_commit_and_judge_diffs_against_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(source, "add", "-A")
    _git(source, "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "-m", "base")
    rev = _git(source, "rev-parse", "HEAD")

    target = tmp_path / "checkout"
    workdir = checkout_pack("unused-origin", rev, target, source=str(source))
    assert workdir == target
    assert _git(target, "rev-parse", "HEAD") == rev

    # a backslashed drive path reads as SCP syntax (host=E) to git; the
    # harness normalizes it to forward slashes
    target2 = tmp_path / "checkout2"
    workdir2 = checkout_pack(
        "unused-origin", rev, target2,
        source=str(source).replace("/", "\\"),
    )
    assert _git(target2, "rev-parse", "HEAD") == rev
    assert workdir2 == target2

    # agent "work": modify the file, then judge against the pinned commit
    (workdir / "app.py").write_text("value = 2\n", encoding="utf-8")
    (workdir / "tests").mkdir()
    suite = tmp_path / "hidden.py"
    suite.write_text("def test_hidden():\n    assert True\n",
                     encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir()
    judge = judge_workspace(
        target, workdir, rev, outdir,
        test_commands=["python -c \"print('graded')\"",
                       "python -c \"raise SystemExit(3)\""],
        hidden_suite=suite,
    )
    assert judge["changed"] is True
    assert judge["results"][0]["exit_code"] == 0
    assert judge["results"][1]["exit_code"] == 3
    assert judge["success"] is False  # one command failed
    assert (outdir / "agent.diff").read_text(encoding="utf-8") != ""
    assert (workdir / "tests" / "hidden.py").is_file()  # suite injected


def test_hidden_suite_resolution(tmp_path: Path) -> None:
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(PACK), encoding="utf-8")
    pack = load_pack(pack_file)
    assert hidden_suite_source(pack_file, pack) is None

    pack = load_pack(_pack_with_suite(tmp_path))
    with pytest.raises(InvalidRequest, match="hidden suite not found"):
        hidden_suite_source(pack_file.with_name("other.json"), pack)
    (tmp_path / "suite.py").write_text("# ok\n", encoding="utf-8")
    assert hidden_suite_source(tmp_path / "with-suite.json", pack) == (
        tmp_path / "suite.py"
    )


def _pack_with_suite(tmp_path: Path) -> Path:
    data = json.loads(json.dumps(PACK))
    data["acceptance"]["hidden_suite"] = "suite.py"
    target = tmp_path / "with-suite.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_hidden_suite_traversal_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "suite.py").write_text("# ok\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    data = json.loads(json.dumps(PACK))
    data["acceptance"]["hidden_suite"] = "../suite.py"
    pack_file = sub / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")
    pack = load_pack(pack_file)
    with pytest.raises(InvalidRequest, match="must live under"):
        hidden_suite_source(pack_file, pack)


def test_normalize_arms_validates_strictly() -> None:
    from specweaver.evaluation.harness import normalize_arms

    assert normalize_arms("on,off") == ["on", "off"]
    assert normalize_arms(" ON ") == ["on"]
    with pytest.raises(InvalidRequest, match="unknown arm"):
        normalize_arms("on,sideways")
    with pytest.raises(InvalidRequest, match="empty"):
        normalize_arms(",,")


def test_stage_given_files_copies_into_workspace(tmp_path: Path) -> None:
    (tmp_path / "givens").mkdir()
    (tmp_path / "givens" / "delta.md").write_text(
        "## MODIFIED Requirements\n", encoding="utf-8"
    )
    data = json.loads(json.dumps(PACK))
    data["task"]["given_files"] = [
        {"src": "givens/delta.md", "dest": "openspec/changes/c1/specs/x/spec.md"}
    ]
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")
    pack = load_pack(pack_file)
    workdir = tmp_path / "ws"
    workdir.mkdir()

    from specweaver.evaluation.harness import stage_given_files

    staged = stage_given_files(pack_file, pack, workdir)
    assert staged == ["openspec/changes/c1/specs/x/spec.md"]
    staged_file = workdir / "openspec" / "changes" / "c1" / "specs" / "x" / "spec.md"
    assert staged_file.read_text(encoding="utf-8") == (
        "## MODIFIED Requirements\n"
    )


def test_stage_given_files_rejects_traversal_and_missing(
    tmp_path: Path,
) -> None:
    from specweaver.evaluation.harness import stage_given_files

    data = json.loads(json.dumps(PACK))
    data["task"]["given_files"] = [
        {"src": "../escape.md", "dest": "x.md"}
    ]
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps(data), encoding="utf-8")
    pack = load_pack(pack_file)
    workdir = tmp_path / "ws"
    workdir.mkdir()
    with pytest.raises(InvalidRequest, match="must live under"):
        stage_given_files(pack_file, pack, workdir)

    data["task"]["given_files"] = [{"src": "givens/none.md", "dest": "x.md"}]
    pack_file.write_text(json.dumps(data), encoding="utf-8")
    pack = load_pack(pack_file)
    with pytest.raises(InvalidRequest, match="given file not found"):
        stage_given_files(pack_file, pack, workdir)


def test_run_workspace_commands_reports_each_result(tmp_path: Path) -> None:
    from specweaver.evaluation.harness import run_workspace_commands

    outdir = tmp_path / "out"
    outdir.mkdir()
    results = run_workspace_commands(
        tmp_path,
        ['python -c "print(1)"', 'python -c "raise SystemExit(3)"'],
        timeout_s=30,
        report_dir=outdir,
        report_prefix="setup",
    )
    assert results[0]["exit_code"] == 0
    assert results[0]["report_ref"] == "setup-0.txt"
    assert results[1]["exit_code"] == 3
    assert (outdir / "setup-1.txt").is_file()


def test_run_workspace_commands_timeout(tmp_path: Path) -> None:
    from specweaver.evaluation.harness import run_workspace_commands

    results = run_workspace_commands(
        tmp_path, ['python -c "import time; time.sleep(30)"'],
        timeout_s=2,
    )
    assert results[0]["exit_code"] is None
    assert "timeout" in results[0]["summary"]


def test_detect_tamper_flags_modify_delete_not_add() -> None:
    from specweaver.evaluation.harness import detect_tamper

    changes = [
        ("A", "tests/new-agent-test.spec.ts"),      # additions are free
        ("M", "tests/book-search.spec.ts"),          # upstream weakened
        ("D", "tests/pagination.spec.ts"),           # upstream deleted
        ("M", "src/api/client.ts"),                  # outside protection
    ]
    tampered = detect_tamper(changes, ["tests"])
    assert sorted(tampered) == [
        "D tests/pagination.spec.ts",
        "M tests/book-search.spec.ts",
    ]


def test_detect_tamper_covers_nested_and_exact_paths() -> None:
    from specweaver.evaluation.harness import detect_tamper

    changes = [
        ("M", "openspec/specs/search-filters/spec.md"),
        ("M", "tests/helpers/mockApi.ts"),
    ]
    tampered = detect_tamper(changes, ["tests", "openspec/specs"])
    assert "M openspec/specs/search-filters/spec.md" in tampered
    assert "M tests/helpers/mockApi.ts" in tampered


def test_judge_fails_on_upstream_test_tampering(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    (source / "tests").mkdir()
    (source / "tests" / "test_upstream.py").write_text(
        "def test_upstream():\n    assert True\n", encoding="utf-8"
    )
    _git(source, "add", "-A")
    _git(source, "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "-m", "base")
    rev = _git(source, "rev-parse", "HEAD")

    target = tmp_path / "checkout"
    workdir = checkout_pack("unused", rev, target, source=str(source))
    (workdir / "app.py").write_text("value = 2\n", encoding="utf-8")
    (workdir / "tests" / "test_upstream.py").write_text(
        "def test_upstream():\n    assert False  # weakened\n",
        encoding="utf-8",
    )
    outdir = tmp_path / "out"
    outdir.mkdir()
    judge = judge_workspace(
        target, workdir, rev, outdir,
        test_commands=["python -c \"print('suite green')\""],
        protected_paths=["tests"],
    )
    assert judge["success"] is False  # suite green, but verdict is failure
    assert judge["tampered"] == ["M tests/test_upstream.py"]
