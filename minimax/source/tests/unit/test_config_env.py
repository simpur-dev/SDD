"""Settings must locate its .env independently of the caller's cwd.

Regression guard for the reproducibility trap: running `specweaver doctor`
from the repo root used to miss specweaver/.env silently and fall back to
rule mode, so the evidence numbers could not be reproduced.
"""
from __future__ import annotations

from pathlib import Path

from specweaver.shared import config
from specweaver.shared.config import Settings


def test_project_env_path_sits_next_to_the_package() -> None:
    pkg_root = Path(config.__file__).resolve().parents[2]  # .../src
    assert Path(config._PROJECT_ENV) == pkg_root.parent / ".env"


def test_cwd_env_overrides_the_project_env(tmp_path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "INFERENCE__PROVIDER=from-cwd\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    assert Settings().inference.provider == "from-cwd"


def test_missing_cwd_env_falls_back_without_raising(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.inference.provider  # project .env, or the "none" default
    assert settings.seekdb.port == 2881
