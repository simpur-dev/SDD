"""Degraded-assembly boundaries: backend bootstrap failure must degrade into
traceable SWError, not raw AttributeError crashes (audit B-11)."""
from __future__ import annotations

import pytest

from specweaver.application.usecases.get_context import GetContextRequest
from specweaver.application.usecases.ingest_project import (
    IngestProjectRequest,
)
from specweaver.shared import di
from specweaver.shared.config import Settings
from specweaver.shared.errors import SWError


def _dead_backends_settings() -> Settings:
    settings = Settings()
    settings.seekdb.host = "127.0.0.1"
    settings.seekdb.port = 1  # instant ECONNREFUSED, no external traffic
    settings.powercontext.base_url = "http://127.0.0.1:1"
    settings.workspace.root = "."
    return settings


async def test_ingest_without_seekdb_raises_swerror() -> None:
    async with di.run(_dead_backends_settings()) as app:
        assert app.catalog is None
        with pytest.raises(SWError):
            await app.usecases["ingest_project"](
                IngestProjectRequest(
                    project_id="ghost", register_source=False
                )
            )


async def test_get_context_without_seekdb_degrades_to_empty_bundle() -> None:
    async with di.run(_dead_backends_settings()) as app:
        result = await app.usecases["get_context"](
            GetContextRequest(project_id="ghost", task_text="任意任务")
        )
        assert result.bundle.budget is not None
        assert result.bundle.budget.used_bytes <= 8000
