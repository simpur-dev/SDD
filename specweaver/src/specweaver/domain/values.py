from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .enums import FindingKind, Severity


class SourceRef(BaseModel):
    """Pointer to the original evidence (file uri + line range)."""

    uri: str
    locator: str | None = None  # e.g. L42-L88
    kind: str | None = None
    checksum: str | None = None


class Citation(BaseModel):
    """A traceable reference to a specific artifact version."""

    artifact_id: str
    version: str | None = None
    source: SourceRef
    updated_at: datetime | None = None


class Finding(BaseModel):
    """Conflict / gap / suspect / unverified observation."""

    kind: FindingKind
    severity: Severity = Severity.warning
    message: str
    refs: list[Citation] = []
    suggestion: str | None = None
    needs_confirmation: bool = False


class Budget(BaseModel):
    max_bytes: int = 8000
    max_items: int | None = None
    used_bytes: int = 0
    truncated: bool = False


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens
