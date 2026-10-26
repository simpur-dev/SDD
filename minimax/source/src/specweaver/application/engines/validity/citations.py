from __future__ import annotations

from ....domain.entities import Artifact
from ....domain.values import Citation, SourceRef


def cite(artifact: Artifact) -> Citation:
    """Build a traceable citation for an artifact, tolerating a missing source."""
    source = artifact.source or SourceRef(uri=artifact.id)
    return Citation(
        artifact_id=artifact.id,
        version=artifact.version,
        source=source,
    )
