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


class ArtifactNotFound(SWError):
    code = "SW-NOTFOUND"
    retriable = False


class ConflictDetected(SWError):
    code = "SW-CONFLICT"
    retriable = False


class InvalidRequest(SWError):
    code = "SW-INVALID"
    retriable = False


class InferenceUnavailable(SWError):
    code = "SW-INFER"
    retriable = True


class StateMismatch(SWError):
    code = "SW-MISMATCH"
    retriable = False
