"""Shared workspace<->catalog consistency check (ResumeTask and VerifyState)."""
from __future__ import annotations

from pydantic import BaseModel

from ...domain.entities import Artifact
from ...domain.ports.catalog import ArtifactFilter, CatalogPort
from ...domain.ports.workspace import WorkspacePort
from ..engines.validity.lifecycle import LifecycleValidator


class StateMismatch(BaseModel):
    artifact_id: str
    source_uri: str
    issue: str


async def check_artifacts(
    artifacts: list[Artifact],
    workspace: WorkspacePort,
    lifecycle: LifecycleValidator | None = None,
) -> list[StateMismatch]:
    """Engineering cross-check: recorded artifact vs the real workspace."""
    validator = lifecycle or LifecycleValidator()
    mismatches: list[StateMismatch] = []
    for artifact in artifacts:
        issue = await validator.verify_engineering(artifact, workspace)
        if issue is not None:
            mismatches.append(
                StateMismatch(
                    artifact_id=artifact.id,
                    source_uri=(
                        artifact.source.uri if artifact.source else ""
                    ),
                    issue=issue,
                )
            )
    return mismatches


async def workspace_mismatches(
    catalog: CatalogPort,
    workspace: WorkspacePort,
    project_id: str,
    lifecycle: LifecycleValidator | None = None,
) -> list[StateMismatch]:
    artifacts = await catalog.list_artifacts(
        ArtifactFilter(project_id=project_id)
    )
    return await check_artifacts(artifacts, workspace, lifecycle)
