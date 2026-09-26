from __future__ import annotations

import csv
import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class SpanRecord:
    name: str
    duration_ms: float = 0.0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    backend_calls: int = 0
    status: str = "ok"
    error: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


# Bucket edges in ms around the observed span costs: pure-assembly spans are
# sub-millisecond, a live get_context with an LLM planner takes seconds.
_DURATION_BUCKETS = (
    1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000
)


def _le_label(edge: float) -> str:
    return str(int(edge)) if float(edge).is_integer() else str(edge)


class Telemetry:
    """Collect per-usecase timing/usage; exports to evidence/usage.csv."""

    def __init__(self) -> None:
        self.trace_id = uuid.uuid4().hex
        self.records: list[SpanRecord] = []
        self._open: list[SpanRecord] = []

    @contextmanager
    def span(self, name: str):
        rec = SpanRecord(name=name)
        start = time.perf_counter()
        self._open.append(rec)
        try:
            yield rec
        except Exception as exc:  # noqa: BLE001
            rec.status = "error"
            rec.error = str(exc)
            raise
        finally:
            self._open.remove(rec)
            rec.duration_ms = (time.perf_counter() - start) * 1000
            self.records.append(rec)

    def current(self) -> SpanRecord | None:
        """Innermost open span, or None outside any span."""
        return self._open[-1] if self._open else None

    def add_token_usage(
        self, rec: SpanRecord, prompt: int = 0, completion: int = 0
    ) -> None:
        rec.llm_calls += 1
        rec.prompt_tokens += prompt
        rec.completion_tokens += completion

    def record_llm_usage(
        self, prompt_tokens: int = 0, completion_tokens: int = 0
    ) -> None:
        """Attribute one completed LLM call to the currently open span."""
        rec = self.current()
        if rec is not None:
            self.add_token_usage(rec, prompt_tokens, completion_tokens)

    def record_backend_call(self) -> None:
        """Attribute one driven-adapter backend operation to the open span."""
        rec = self.current()
        if rec is not None:
            rec.backend_calls += 1

    def record_metric(self, key: str, value: float) -> None:
        """Engine-level metric on the currently open span (docs/03 §11)."""
        rec = self.current()
        if rec is not None:
            rec.metrics[key] = value

    def snapshot(self) -> list[dict]:
        rows = []
        for rec in self.records:
            row = rec.__dict__.copy()
            row["metrics"] = json.dumps(rec.metrics, ensure_ascii=False)
            rows.append(row)
        return rows

    def to_csv(self, path: str) -> None:
        rows = self.snapshot()
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def to_prometheus(self) -> str:
        """Prometheus text exposition (0.0.4), aggregated per span name."""
        agg: dict[str, dict[str, float]] = {}
        durations: dict[str, list[float]] = {}
        engine: dict[tuple[str, str], float] = {}
        for rec in self.records:
            a = agg.setdefault(
                rec.name,
                {
                    "count": 0, "duration": 0, "llm": 0, "prompt": 0,
                    "completion": 0, "backend": 0, "errors": 0,
                },
            )
            a["count"] += 1
            a["duration"] += rec.duration_ms
            a["llm"] += rec.llm_calls
            a["prompt"] += rec.prompt_tokens
            a["completion"] += rec.completion_tokens
            a["backend"] += rec.backend_calls
            a["errors"] += 1 if rec.status == "error" else 0
            durations.setdefault(rec.name, []).append(rec.duration_ms)
            for key, value in rec.metrics.items():
                engine[(rec.name, key)] = engine.get(
                    (rec.name, key), 0.0
                ) + float(value)

        lines: list[str] = []

        def family(
            name: str, help_text: str, typ: str, values: dict[str, float]
        ) -> None:
            if not values:
                return
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {typ}")
            for span, value in sorted(values.items()):
                lines.append(f'{name}{{span="{span}"}} {round(value, 3)}')

        family("sw_spans_total", "Completed spans by usecase.", "counter",
               {k: v["count"] for k, v in agg.items()})
        family("sw_errors_total", "Failed spans by usecase.", "counter",
               {k: v["errors"] for k, v in agg.items()})
        family("sw_llm_calls_total", "LLM completions by usecase.",
               "counter", {k: v["llm"] for k, v in agg.items()})
        family("sw_llm_prompt_tokens_total", "Prompt tokens by usecase.",
               "counter", {k: v["prompt"] for k, v in agg.items()})
        family("sw_llm_completion_tokens_total",
               "Completion tokens by usecase.", "counter",
               {k: v["completion"] for k, v in agg.items()})
        family("sw_backend_calls_total", "Backend operations by usecase.",
               "counter", {k: v["backend"] for k, v in agg.items()})
        if durations:
            # A real histogram so `histogram_quantile(0.95, ...)` works - the
            # official memory-layer benchmark reports p95, so we expose it too
            # instead of only sums.
            lines.append("# HELP sw_span_duration_ms Span duration in ms.")
            lines.append("# TYPE sw_span_duration_ms histogram")
            for span in sorted(durations):
                samples = durations[span]
                total = sum(samples)
                for le in _DURATION_BUCKETS:
                    count = sum(1 for s in samples if s <= le)
                    lines.append(
                        f'sw_span_duration_ms_bucket{{span="{span}",'
                        f'le="{_le_label(le)}"}} {count}'
                    )
                lines.append(
                    f'sw_span_duration_ms_bucket{{span="{span}",le="+Inf"}} '
                    f"{len(samples)}"
                )
                lines.append(
                    f'sw_span_duration_ms_sum{{span="{span}"}} '
                    f"{round(total, 3)}"
                )
                lines.append(
                    f'sw_span_duration_ms_count{{span="{span}"}} '
                    f"{len(samples)}"
                )
        if engine:
            lines.append("# HELP sw_engine_metric_sum Engine metrics summed"
                         " by usecase (recall, findings, bundle_bytes...)")
            lines.append("# TYPE sw_engine_metric_sum gauge")
            for (span, key), value in sorted(engine.items()):
                lines.append(
                    f'sw_engine_metric_sum{{span="{span}",metric="{key}"}} '
                    f"{round(value, 3)}"
                )
        lines.append(f"# trace_id {self.trace_id}")
        return "\n".join(lines) + "\n"
