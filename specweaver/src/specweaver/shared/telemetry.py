from __future__ import annotations

import csv
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass


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

    def snapshot(self) -> list[dict]:
        return [r.__dict__ for r in self.records]

    def to_csv(self, path: str) -> None:
        rows = self.snapshot()
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
