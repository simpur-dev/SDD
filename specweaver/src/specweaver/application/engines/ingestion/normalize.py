from __future__ import annotations

import hashlib
import re
from datetime import datetime

from ....domain.entities import Artifact
from ....domain.enums import ArtifactType, LifecycleStatus
from ....domain.values import SourceRef
from .parsers.base import ParsedDocument

_PREFIX = {
    ArtifactType.requirement: "REQ",
    ArtifactType.design: "DES",
    ArtifactType.code: "CODE",
    ArtifactType.test: "TST",
    ArtifactType.rule: "RULE",
}
_EXPLICIT_ID_RE = re.compile(r"^(REQ|DES|CODE|TST|RULE)[-_ ]?(\d+)$")
_STATUS_MAP = {
    "draft": LifecycleStatus.draft,
    "active": LifecycleStatus.active,
    "superseded": LifecycleStatus.superseded,
    "deprecated": LifecycleStatus.deprecated,
}


def artifact_id(doc: ParsedDocument) -> str:
    """Stable id: explicit front-matter id wins, else content-hash of the path."""
    explicit = doc.front_matter.get("id")
    if isinstance(explicit, str) and explicit.strip():
        match = _EXPLICIT_ID_RE.match(explicit.strip().upper())
        if match:
            return f"{match.group(1)}-{int(match.group(2))}"
        return explicit.strip()
    prefix = _PREFIX[doc.type]
    digest = hashlib.sha1(doc.path.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _module(path: str) -> str | None:
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else None


def _status(value: object) -> LifecycleStatus:
    if isinstance(value, str):
        return _STATUS_MAP.get(value.strip().lower(), LifecycleStatus.active)
    return LifecycleStatus.active


def _tags(raw: object, artifact_type: ArtifactType) -> list[str]:
    tags = [artifact_type.value]
    if isinstance(raw, str):
        tags.extend(t.strip() for t in raw.split(",") if t.strip())
    return list(dict.fromkeys(tags))


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def to_artifact(project_id: str, doc: ParsedDocument) -> Artifact:
    fm = doc.front_matter
    return Artifact(
        id=artifact_id(doc),
        project_id=project_id,
        type=doc.type,
        module=_module(doc.path),
        title=doc.title,
        content=doc.raw_text,
        version=str(fm.get("version", "0.1.0")),
        status=_status(fm.get("status")),
        effective_from=_parse_date(fm.get("effective_from")),
        effective_to=_parse_date(fm.get("effective_to")),
        applies_to_ref=fm.get("applies_to"),
        supersedes=fm.get("supersedes"),
        source=SourceRef(uri=doc.path, checksum=doc.checksum),
        checksum=doc.checksum,
        tags=_tags(fm.get("tags"), doc.type),
        based_on=list(doc.references),
    )
