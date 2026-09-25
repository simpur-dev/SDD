from __future__ import annotations

import asyncio

from ....domain.ports.catalog import HybridQuery, ScoredArtifact
from .client import SeekdbClient
from .schema import record_to_artifact


def _where(query: HybridQuery) -> dict:
    conds = [{"project_id": {"$eq": query.project_id}}]
    if query.types:
        conds.append({"type": {"$in": [t.value for t in query.types]}})
    if query.modules:
        conds.append({"module": {"$in": query.modules}})
    if query.only_active:
        conds.append({"status": {"$eq": "active"}})
    return conds[0] if len(conds) == 1 else {"$and": conds}


class SeekdbHybridSearch:
    def __init__(self, client: SeekdbClient) -> None:
        self._client = client

    async def hybrid_search(self, query: HybridQuery) -> list[ScoredArtifact]:
        def _op() -> list[ScoredArtifact]:
            collection = self._client.artifacts
            where = _where(query)
            use_semantic = query.use_semantic and query.query_embedding is not None

            if use_semantic:
                res = collection.hybrid_search(
                    query={
                        "where_document": {"$contains": query.text},
                        "where": where,
                        "n_results": query.n_results,
                    },
                    knn={
                        "query_embeddings": [query.query_embedding],
                        "where": where,
                        "n_results": query.n_results,
                    },
                    rank={"rrf": {}},
                    n_results=query.n_results,
                    include=["documents", "metadatas", "embeddings"],
                )
                ids = res["ids"][0]
                docs = res["documents"][0]
                metas = res["metadatas"][0]
                embs = res.get("embeddings", [[None] * len(ids)])[0]
                dist = res.get("distances", [[0.0] * len(ids)])[0]
            else:
                res = collection.get(
                    where_document={"$contains": query.text},
                    where=where,
                    limit=query.n_results,
                    include=["documents", "metadatas", "embeddings"],
                )
                ids = res["ids"]
                docs = res["documents"]
                metas = res["metadatas"]
                embs = res.get("embeddings", [None] * len(ids))
                dist = [0.0] * len(ids)

            out: list[ScoredArtifact] = []
            for i, aid in enumerate(ids):
                artifact = record_to_artifact(aid, docs[i], metas[i], embs[i])
                out.append(
                    ScoredArtifact(artifact=artifact, score=float(dist[i] or 0.0))
                )
            return out

        return await asyncio.to_thread(_op)
