from __future__ import annotations

from ...shared.telemetry import Telemetry


class UseCase:
    """Base class: a callable request handler with a telemetry span."""

    name: str = "usecase"

    def __init__(self, telemetry: Telemetry) -> None:
        self.telemetry = telemetry

    def span(self):
        return self.telemetry.span(self.name)
