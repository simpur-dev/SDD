"""TaskPack schema, isolation materialization, and asset regression."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specweaver.application.engines.ingestion.profiles import known_profiles
from specweaver.evaluation.taskpack import (
    load_dir,
    load_pack,
    materialize,
)
from specweaver.shared.errors import InvalidRequest

TASKPACKS = Path(__file__).resolve().parents[2] / "taskpacks"

MINIMAL = {
    "id": "demo-basic",
    "tier": "basic",
    "repo": {"origin": "https://example.invalid/demo.git", "commit": "abc1234"},
    "agent": {"name": "claude-code", "version": "1.0", "model": "test-model"},
    "task": {"goal": "do the thing"},
    "acceptance": {"test_commands": ["python -m pytest -q"]},
}


def _write(tmp_path: Path, data: object, name: str = "pack.json") -> Path:
    target = tmp_path / name
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return target


def test_minimal_manifest_loads_with_defaults(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, MINIMAL))
    assert pack.schema_version == 1
    assert pack.title == ""
    assert pack.repo.subdir == ""
    assert pack.repo.profile == "auto"
    assert pack.snapshot.seekdb == "fresh"
    assert pack.snapshot.powercontext_scope == "fresh"
    assert pack.budget.max_tokens is None
    assert pack.agent.tool_allowlist == []
    assert pack.acceptance.forbidden_regressions == []


def test_unknown_field_is_rejected_and_named(tmp_path: Path) -> None:
    stray = dict(MINIMAL, comit="typo-in-repo")  # top-level stray field
    with pytest.raises(InvalidRequest, match="comit"):
        load_pack(_write(tmp_path, stray))


def test_missing_required_field_is_rejected(tmp_path: Path) -> None:
    broken = {k: v for k, v in MINIMAL.items() if k != "acceptance"}
    with pytest.raises(InvalidRequest, match="acceptance"):
        load_pack(_write(tmp_path, broken))


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"id": "Bad_ID"}, "id"),
        ({"tier": "medium"}, "tier"),
        ({"schema_version": 2}, "schema_version"),
    ],
)
def test_enums_and_patterns_are_enforced(
    tmp_path: Path, override: dict, fragment: str
) -> None:
    with pytest.raises(InvalidRequest, match=fragment):
        load_pack(_write(tmp_path, dict(MINIMAL, **override)))


def test_unknown_profile_name_is_rejected(tmp_path: Path) -> None:
    data = json.loads(json.dumps(MINIMAL))
    data["repo"]["profile"] = "nope"
    with pytest.raises(InvalidRequest, match="nope"):
        load_pack(_write(tmp_path, data))


def test_empty_test_commands_and_bad_budget_are_rejected(tmp_path: Path) -> None:
    data = json.loads(json.dumps(MINIMAL))
    data["acceptance"]["test_commands"] = []
    with pytest.raises(InvalidRequest, match="test_commands"):
        load_pack(_write(tmp_path, data))

    data["acceptance"]["test_commands"] = ["python -m pytest -q"]
    data["budget"] = {"max_tokens": -1}
    with pytest.raises(InvalidRequest, match="max_tokens"):
        load_pack(_write(tmp_path, data))


def test_tool_allowlist_requires_sw_prefix(tmp_path: Path) -> None:
    data = json.loads(json.dumps(MINIMAL))
    data["agent"]["tool_allowlist"] = ["get_context"]
    with pytest.raises(InvalidRequest, match="sw_"):
        load_pack(_write(tmp_path, data))


def test_load_dir_sorts_and_names_bad_files(tmp_path: Path) -> None:
    _write(tmp_path, dict(MINIMAL, id="pack-b"), "b.json")
    _write(tmp_path, dict(MINIMAL, id="pack-a", tier="advanced"), "a.json")
    packs = load_dir(tmp_path)
    assert [p.id for p in packs] == ["pack-a", "pack-b"]

    (tmp_path / "c.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(InvalidRequest, match="c.json"):
        load_dir(tmp_path)


def test_materialize_derives_isolated_identities(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, MINIMAL))
    first = materialize(pack, "run1", "/tmp/work")
    assert first.project_id == "demo-basic-run1"
    assert first.scope_title == "sw:demo-basic-run1"
    assert first.workspace_dir.replace("\\", "/").endswith("demo-basic-run1")
    assert first.profile == "auto"

    second = materialize(pack, "run2", "/tmp/work")
    assert second.project_id != first.project_id
    assert second.scope_title != first.scope_title
    assert second.workspace_dir != first.workspace_dir

    assert json.loads(json.dumps(first.summary()))["tier"] == "basic"


def test_materialize_rejects_blank_or_bad_run_id(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, MINIMAL))
    for bad in ("", "   ", "bad id!", "x" * 100):
        with pytest.raises(InvalidRequest, match="run_id"):
            materialize(pack, bad, "/tmp/work")


def test_shipped_assets_load_and_cover_all_tiers() -> None:
    packs = load_dir(TASKPACKS)
    assert {p.tier for p in packs} == {"basic", "advanced", "challenge"}
    assert all(p.id.startswith("railway-") for p in packs)
    for pack in packs:
        assert pack.repo.commit
        assert pack.repo.profile in known_profiles()
        assert all(t.startswith("sw_") for t in pack.agent.tool_allowlist)
        assert pack.snapshot.seekdb == "fresh"
        assert pack.budget.time_limit_s and pack.budget.max_tokens


def test_manifest_round_trip_is_lossless(tmp_path: Path) -> None:
    pack = load_pack(_write(tmp_path, MINIMAL))
    again = load_pack(
        _write(tmp_path, pack.model_dump(mode="json"), "round.json")
    )
    assert again == pack
