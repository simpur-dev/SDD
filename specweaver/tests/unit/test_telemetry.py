from __future__ import annotations

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
