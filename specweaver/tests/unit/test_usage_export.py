"""SPECWEAVER_USAGE_OUT export hook on the stdio server's exit path."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from specweaver.adapters.driving.mcp.run_stdio import export_usage
from specweaver.shared.telemetry import Telemetry


class _AppStub:
    """SpecWeaverApp surface used by export_usage: just the telemetry."""

    def __init__(self, telemetry: Telemetry) -> None:
        self.telemetry = telemetry


def test_export_writes_csv_when_env_set(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "usage.csv"
    monkeypatch.setenv("SPECWEAVER_USAGE_OUT", str(target))
    telemetry = Telemetry()
    with telemetry.span("get_context") as record:
        telemetry.record_metric("findings", 2)
        telemetry.record_llm_usage(prompt_tokens=10, completion_tokens=5)
    assert record.llm_calls == 1  # sanity: record landed on the span

    export_usage(_AppStub(telemetry))

    with target.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["name"] == "get_context"
    assert json.loads(rows[0]["metrics"])["findings"] == 2.0


def test_export_is_silent_noop_without_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SPECWEAVER_USAGE_OUT", raising=False)
    telemetry = Telemetry()
    with telemetry.span("get_context"):
        pass
    export_usage(_AppStub(telemetry))
    assert not (tmp_path / "usage.csv").exists()


def test_export_failure_degrades_to_warning(tmp_path: Path, monkeypatch,
                                            capsys) -> None:
    blocking = tmp_path / "usage.csv"
    blocking.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SPECWEAVER_USAGE_OUT", str(blocking / "child.csv"))
    telemetry = Telemetry()
    with telemetry.span("get_context"):
        pass  # a closed span is kept, so to_csv actually attempts the write
    export_usage(_AppStub(telemetry))  # must not raise
    assert "[warn] usage export" in capsys.readouterr().err
