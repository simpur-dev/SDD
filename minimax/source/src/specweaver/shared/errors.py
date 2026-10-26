from __future__ import annotations


class SWError(Exception):
    """Base error for SpecWeaver."""

    code: str = "SW-ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BackendConnectionError(SWError):
    code = "SW-BACKEND"


class InvalidRequest(SWError):
    code = "SW-INVALID"


class InferenceUnavailable(SWError):
    code = "SW-INFER"
