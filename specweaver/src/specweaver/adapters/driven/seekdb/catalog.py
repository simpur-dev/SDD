from __future__ import annotations

import asyncio

from ....domain.entities import Artifact, Relation
from ....domain.ports.catalog import ArtifactFilter
from .client import RELATIONS_TABLE, SeekdbClient
from .schema import artifact_to_record, record_to_artifact


def _scalar_where(flt: ArtifactFilter) -> dict | None:
    conds = [{"project_id": {"$eq": flt.project_id}}]
    if flt.types:
        conds.append({"type": {"$in": [t.value for t in flt.types]}})
    if flt.modules:
        conds.append({"module": {"$in": flt.modules}})
    if flt.status:
        conds.append({"status": {"$eq": flt.status.value}})
    return conds[0] if len(conds) == 1 else {"$and": conds}


class SeekdbCatalog:
    def __init__(self, client: SeekdbClient) -> None:
        self._client = client

    # ----- artifacts --------------------------------------------------------
    async def upsert_artifact(self, artifact: Artifact) -> None:
        rec = artifact_to_record(artifact)
        collection = self._client.artifacts

        def _op() -> None:
            collection.upsert(
                ids=rec["id"],
                documents=rec["document"],
                embeddings=rec["embedding"],
                metadatas=rec["metadata"],
            )

        await asyncio.to_thread(_op)

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        collection = self._client.artifacts

        def _op() -> Artifact | None:
            res = collection.get(
                ids=[artifact_id],
                include=["documents", "metadatas", "embeddings"],
            )
            if not res["ids"]:
                return None
            return record_to_artifact(
                res["ids"][0],
                res["documents"][0],
                res["metadatas"][0],
                res.get("embeddings", [None])[0],
            )

        return await asyncio.to_thread(_op)

    async def list_artifacts(self, flt: ArtifactFilter) -> list[Artifact]:
        collection = self._client.artifacts
        where = _scalar_where(flt)

        def _op() -> list[Artifact]:
            res = collection.get(
                where=where,
                include=["documents", "metadatas", "embeddings"],
                limit=1000,
            )
            items = []
            embeddings = res.get("embeddings", [None] * len(res["ids"]))
            for i, aid in enumerate(res["ids"]):
                items.append(
                    record_to_artifact(
                        aid,
                        res["documents"][i],
                        res["metadatas"][i],
                        embeddings[i],
                    )
                )
            return items

        items = await asyncio.to_thread(_op)
        if flt.ref:
            items = [
                a
                for a in items
                if not a.applies_to_ref or flt.ref in a.applies_to_ref
            ]
        return items

    # ----- relations --------------------------------------------------------
    async def upsert_relation(self, relation: Relation) -> None:
        edge_id = SeekdbClient.edge_id(
            relation.src, relation.kind.value, relation.dst
        )
        sql = (
            f"INSERT INTO {RELATIONS_TABLE} "
            "(edge_id,project_id,src_id,dst_id,kind,confidence,evidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE confidence=VALUES(confidence), "
            "evidence=VALUES(evidence), project_id=VALUES(project_id)"
        )
        args = (
            edge_id,
            relation.project_id,
            relation.src,
            relation.dst,
            relation.kind.value,
            relation.confidence,
            relation.evidence,
        )

        def _op() -> None:
            raw = self._client.raw_connection()
            with raw.cursor() as cur:
                cur.execute(sql, args)

        await asyncio.to_thread(_op)

    async def neighbors(
        self, artifact_id: str, kinds, depth: int = 1
    ) -> list[Artifact]:
        kind_values = [k.value for k in kinds]

        def _op() -> list[Artifact]:
            raw = self._client.raw_connection()
            visited = {artifact_id}
            frontier = [artifact_id]
            found: set[str] = set()
            for _ in range(depth):
                if not frontier:
                    break
                placeholders = ",".join(["%s"] * len(frontier))
                kind_ph = ",".join(["%s"] * len(kind_values))
                params = tuple(frontier) + tuple(kind_values)
                with raw.cursor() as cur:
                    cur.execute(
                        f"SELECT dst_id FROM {RELATIONS_TABLE} "
                        f"WHERE src_id IN ({placeholders}) AND kind IN ({kind_ph}) "
                        f"UNION "
                        f"SELECT src_id FROM {RELATIONS_TABLE} "
                        f"WHERE dst_id IN ({placeholders}) AND kind IN ({kind_ph})",
                        params + params,
                    )
                    peers = {r["dst_id"] for r in cur.fetchall()}
                new = peers - visited
                visited |= new
                found |= new
                frontier = list(new)
            if not found:
                return []
            res = self._client.artifacts.get(
                ids=list(found),
                include=["documents", "metadatas", "embeddings"],
            )
            out = []
            embeddings = res.get("embeddings", [None] * len(res["ids"]))
            for i, aid in enumerate(res["ids"]):
                out.append(
                    record_to_artifact(
                        aid,
                        res["documents"][i],
                        res["metadatas"][i],
                        embeddings[i],
                    )
                )
            return out

        return await asyncio.to_thread(_op)
