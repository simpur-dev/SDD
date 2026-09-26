"""ExplainSource: trace an artifact back to its evidence through the catalog.

Returns the artifact's own source pointer, its upstream based_on chain
(recursive, dangling refs surfaced) and downstream neighbours from the
relation graph - the machine-readable answer to "why should I trust this".
"""
from __future__ import annotations

from pydantic import BaseModel

from ...domain.entities import Artifact
from ...domain.enums import RelationKind
from ...domain.ports.catalog import CatalogPort
from ...shared.errors import SWError
from .base import UseCase

_ALL_KINDS = list(RelationKind)
_MAX_DEPTH = 3


class ExplainSourceRequest(BaseModel):
    project_id: str
    artifact_id: str
    depth: int = 1


class SourceNode(BaseModel):
    id: str
    type: str
    status: str
    version: str
    title: str = ""
    module: str | None = None
    source_uri: str | None = None
    checksum: str | None = None


class ExplainSourceReport(BaseModel):
    root: SourceNode
    upstream: list[SourceNode] = []
    downstream: list[SourceNode] = []
    missing_refs: list[str] = []


def _node(artifact: Artifact) -> SourceNode:
    return SourceNode(
        id=artifact.id,
        type=artifact.type.value,
        status=artifact.status.value,
        version=artifact.version,
        title=artifact.title,
        module=artifact.module,
        source_uri=artifact.source.uri if artifact.source else None,
        checksum=artifact.checksum,
    )


class ExplainSource(UseCase):
    """Citation chain for one artifact: source, upstream refs, downstream."""

    name = "explain_source"

    def __init__(
        self, catalog: CatalogPort | None, telemetry
    ) -> None:
        super().__init__(telemetry)
        self._catalog = catalog

    async def __call__(
        self, request: ExplainSourceRequest
    ) -> ExplainSourceReport:
        with self.span():
            if self._catalog is None:
                raise SWError(
                    "explain_source requires the seekdb catalog; "
                    "run `specweaver doctor`"
                )
            root = await self._catalog.get_artifact(
                request.project_id, request.artifact_id
            )
            if root is None:
                raise SWError(
                    "unknown artifact "
                    f"{request.project_id}/{request.artifact_id}"
                )
            depth = max(1, min(request.depth, _MAX_DEPTH))
            report = ExplainSourceReport(root=_node(root))
            seen = {root.id}
            frontier = [root]
            for _ in range(depth):
                next_frontier: list[Artifact] = []
                for artifact in frontier:
                    for ref in artifact.based_on:
                        if ref == artifact.id:
                            continue
                        upstream = await self._catalog.get_artifact(
                            request.project_id, ref
                        )
                        if upstream is None:
                            if ref not in report.missing_refs:
                                report.missing_refs.append(ref)
                            continue
                        if upstream.id in seen:
                            continue
                        seen.add(upstream.id)
                        report.upstream.append(_node(upstream))
                        next_frontier.append(upstream)
                frontier = next_frontier
                if not frontier:
                    break
            peers = await self._catalog.neighbors(
                request.project_id, root.id, _ALL_KINDS, depth=depth
            )
            for peer in peers:
                if peer.id not in seen:
                    seen.add(peer.id)
                    report.downstream.append(_node(peer))
            return report
