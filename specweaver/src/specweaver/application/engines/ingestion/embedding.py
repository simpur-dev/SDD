from __future__ import annotations

from ....domain.entities import Artifact
from ....domain.ports.inference import EmbeddingGatewayPort

_SEARCHABLE_HEAD_CHARS = 1500


def searchable_text(artifact: Artifact) -> str:
    """Compact text used for embeddings: title plus the head of the content."""
    return f"{artifact.title}\n{artifact.content[:_SEARCHABLE_HEAD_CHARS]}"


class ArtifactEmbedder:
    """Populates embeddings for artifacts in a single batched gateway call."""

    def __init__(self, gateway: EmbeddingGatewayPort) -> None:
        self._gateway = gateway

    async def embed(self, artifacts: list[Artifact]) -> None:
        if not artifacts:
            return
        texts = [searchable_text(artifact) for artifact in artifacts]
        vectors = await self._gateway.embed(texts, kind="db")
        for artifact, vector in zip(artifacts, vectors, strict=True):
            artifact.embedding = vector
