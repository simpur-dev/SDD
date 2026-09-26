"""Workspace/git and graph-mining boundary pins from the M4 boundary audit."""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from specweaver.adapters.driven.workspace.git import GitWorkspace
from specweaver.application.engines.ingestion.graph_mining import (
    mine_relations,
)
from specweaver.application.engines.ingestion.normalize import to_artifact
from specweaver.application.engines.ingestion.parsers.markdown import (
    MarkdownParser,
)
from specweaver.domain.enums import ArtifactType
from specweaver.shared.config import WorkspaceSettings


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def test_changed_files_reports_unicode_paths_verbatim(tmp_path: Path) -> None:
    git = subprocess.run(
        ["git", "--version"], capture_output=True
    )
    if git.returncode != 0:
        pytest.skip("git unavailable")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "user.email", "t@t")
    target = tmp_path / "中文需求.md"
    target.write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    target.write_text("v2\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "change")
    head = _git(tmp_path, "rev-parse", "HEAD").strip()

    workspace = GitWorkspace(WorkspaceSettings(root=str(tmp_path)))
    changes = asyncio.run(workspace.changed_files(base, head))
    assert [c.path for c in changes] == ["中文需求.md"]


def test_self_reference_edge_is_minted_today() -> None:
    """Audit B-15 (documented current behaviour): a file containing its own
    id token mints a self-loop edge (REQ-1 refines REQ-1)."""
    text = "---\nid: REQ-01\n---\n# 标题\n- 见 REQ-1 说明\n"
    doc = MarkdownParser().parse(
        "specs/a.md", text, "sha256:a", ArtifactType.requirement
    )
    artifact = to_artifact("p", doc)
    relations = mine_relations("p", [(doc, artifact)])
    self_loops = [r for r in relations if r.src == r.dst]
    # pin current behaviour; flip to the guard expectation when fixed
    assert len(self_loops) == 1
