from __future__ import annotations

import csv
import json

import pytest

from specweaver.shared.telemetry import Telemetry


def test_current_is_none_outside_spans() -> None:
    tel = Telemetry()
    assert tel.current() is None
    tel.record_llm_usage(1, 2)  # must not raise
    tel.record_backend_call()
    assert tel.records == []


def test_records_attach_to_innermost_open_span() -> None:
    tel = Telemetry()
    with tel.span("outer") as outer:
        tel.record_backend_call()
        with tel.span("inner"):
            assert tel.current() is not outer
            tel.record_llm_usage(3, 4)
            tel.record_backend_call()
        assert tel.current() is outer
        tel.record_backend_call()
    by_name = {r.name: r for r in tel.records}
    assert by_name["outer"].llm_calls == 0
    assert by_name["outer"].backend_calls == 2
    assert by_name["inner"].llm_calls == 1
    assert by_name["inner"].prompt_tokens == 3
    assert by_name["inner"].completion_tokens == 4
    assert by_name["inner"].backend_calls == 1


def test_span_stack_unwinds_on_error() -> None:
    tel = Telemetry()
    with pytest.raises(RuntimeError):
        with tel.span("boom"):
            raise RuntimeError("x")
    assert tel.current() is None
    assert tel.records[0].status == "error"


def test_record_metric_attaches_to_innermost_span() -> None:
    tel = Telemetry()
    tel.record_metric("recall", 99)  # outside any span: ignored
    with tel.span("get_context"):
        tel.record_metric("recall", 5)
        with tel.span("retrieval"):
            tel.record_metric("hybrid_ms", 1.5)
    by_name = {r.name: r for r in tel.records}
    assert by_name["get_context"].metrics == {"recall": 5}
    assert by_name["retrieval"].metrics == {"hybrid_ms": 1.5}


def test_snapshot_and_csv_carry_metrics_as_json(tmp_path) -> None:
    tel = Telemetry()
    with tel.span("get_context"):
        tel.record_metric("findings", 2)
    assert tel.snapshot()[0]["metrics"] == '{"findings": 2}'

    path = tmp_path / "usage.csv"
    tel.to_csv(str(path))
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert "metrics" in rows[0]
    assert json.loads(rows[0]["metrics"]) == {"findings": 2.0}


def _expositions(text: str) -> dict[str, float]:
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        key, _, value = line.rpartition(" ")
        values[key] = float(value)
    return values


def test_to_prometheus_aggregates_by_span_name() -> None:
    tel = Telemetry()
    for _ in range(2):
        with tel.span("get_context"):
            tel.record_llm_usage(10, 2)
            tel.record_backend_call()
            tel.record_metric("recall", 4)
    with pytest.raises(ZeroDivisionError):
        with tel.span("get_context"):
            raise ZeroDivisionError("boom")

    values = _expositions(tel.to_prometheus())
    span = '{span="get_context"}'
    assert values[f"sw_spans_total{span}"] == 3
    assert values[f"sw_errors_total{span}"] == 1
    assert values[f"sw_llm_calls_total{span}"] == 2
    assert values[f"sw_llm_prompt_tokens_total{span}"] == 20
    assert values[f"sw_llm_completion_tokens_total{span}"] == 4
    assert values[f"sw_backend_calls_total{span}"] == 2
    assert (
        values['sw_engine_metric_sum{span="get_context",metric="recall"}']
        == 8
    )
    assert values[f"sw_span_duration_ms_sum{span}"] > 0


def test_to_prometheus_is_valid_exposition_text() -> None:
    tel = Telemetry()
    with tel.span("ingest_project"):
        pass
    lines = tel.to_prometheus().splitlines()
    text = "\n".join(lines)
    assert "# TYPE sw_spans_total counter" in text
    assert lines[0].startswith("# HELP ")
    assert lines[-1] == f"# trace_id {tel.trace_id}"
    # a gauge line only appears once the engine recorded one
    assert "sw_engine_metric_sum" not in text


def test_to_prometheus_is_empty_without_spans() -> None:
    values = _expositions(Telemetry().to_prometheus())
    assert values == {}
