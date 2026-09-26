from __future__ import annotations

import json
from datetime import datetime

from ....domain.entities import Artifact
from ....domain.enums import ArtifactType, LifecycleStatus
from ....domain.values import SourceRef


def _dt_iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _loads_list(value: str | None) -> list:
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def storage_key(project_id: str, artifact_id: str) -> str:
    """Collection record key: logical ids collide across projects (REQ-1)."""
    return f"{project_id}:{artifact_id}"


def artifact_to_record(artifact: Artifact) -> dict:
    """Map an Artifact to a pyseekdb collection record (id/document/embedding/metadata)."""
    source = artifact.source
    metadata = {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "type": artifact.type.value,
        "module": artifact.module or "",
        "title": artifact.title,
        "version": artifact.version,
        "status": artifact.status.value,
        "effective_from": _dt_iso(artifact.effective_from),
        "effective_to": _dt_iso(artifact.effective_to),
        "applies_to_ref": artifact.applies_to_ref or "",
        "supersedes": artifact.supersedes or "",
        "superseded_by": artifact.superseded_by or "",
        "source_uri": source.uri if source else "",
        "source_locator": source.locator if source else "",
        "checksum": artifact.checksum or "",
        "tags": json.dumps(artifact.tags, ensure_ascii=False),
        "based_on": json.dumps(artifact.based_on, ensure_ascii=False),
    }
    return {
        "id": artifact.id,
        "document": artifact.content,
        "embedding": artifact.embedding,
        "metadata": metadata,
    }


def record_to_artifact(
    artifact_id: str,
    document: str | None,
    metadata: dict | None,
    embedding: list[float] | None = None,
) -> Artifact:
    m = metadata or {}
    source_uri = m.get("source_uri", "")
    source_checksum = m.get("checksum") or None
    logical_id = m.get("id") or artifact_id
    source = (
        SourceRef(
            uri=source_uri,
            locator=m.get("source_locator") or None,
            checksum=source_checksum,
        )
        if source_uri
        else None
    )
    return Artifact(
        id=logical_id,
        project_id=m.get("project_id", ""),
        type=ArtifactType(m.get("type", "requirement")),
        module=m.get("module") or None,
        title=m.get("title", ""),
        content=document or "",
        version=m.get("version", "0.1.0"),
        status=LifecycleStatus(m.get("status", "active")),
        effective_from=_parse_dt(m.get("effective_from")),
        effective_to=_parse_dt(m.get("effective_to")),
        applies_to_ref=m.get("applies_to_ref") or None,
        supersedes=m.get("supersedes") or None,
        superseded_by=m.get("superseded_by") or None,
        source=source,
        checksum=m.get("checksum") or None,
        tags=_loads_list(m.get("tags")),
        based_on=_loads_list(m.get("based_on")),
        embedding=embedding,
    )
