from __future__ import annotations


class SWError(Exception):
    """Base error for SpecWeaver."""

    code: str = "SW-ERROR"
    retriable: bool = False

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BackendConnectionError(SWError):
    code = "SW-BACKEND"
    retriable = True


class InvalidRequest(SWError):
    code = "SW-INVALID"
    retriable = False


class InferenceUnavailable(SWError):
    code = "SW-INFER"
    retriable = True
