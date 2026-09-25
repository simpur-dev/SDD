from __future__ import annotations

import hashlib

import pymysql
import pyseekdb

from ....shared.config import SeekDbSettings

ARTIFACTS_COLLECTION = "sw_artifacts"
RELATIONS_TABLE = "sw_relations"

_RELATIONS_DDL = f"""
CREATE TABLE IF NOT EXISTS {RELATIONS_TABLE} (
  edge_id     VARCHAR(64) PRIMARY KEY,
  project_id  VARCHAR(64),
  src_id      VARCHAR(96),
  dst_id      VARCHAR(96),
  kind        VARCHAR(32),
  confidence  DOUBLE,
  evidence    VARCHAR(1024),
  UNIQUE KEY uq_edge (src_id, dst_id, kind)
) ORGANIZATION HEAP
"""


class SeekdbClient:
    """Owns the pyseekdb remote client; artifacts use a Collection, relations use a SQL table."""

    def __init__(self, settings: SeekDbSettings, dimension: int) -> None:
        self._settings = settings
        self._dimension = dimension
        self._client = None
        self.artifacts = None

    def initialize(self) -> None:
        s = self._settings
        bootstrap = pymysql.connect(
            host=s.host,
            port=s.port,
            user=s.user,
            password=s.password.get_secret_value(),
            autocommit=True,
            connect_timeout=10,
        )
        try:
            bootstrap.cursor().execute(
                f"CREATE DATABASE IF NOT EXISTS `{s.database}`"
            )
        finally:
            bootstrap.close()

        self._client = pyseekdb.RemoteServerClient(
            host=s.host,
            port=s.port,
            tenant="sys",
            database=s.database,
            user=s.user,
            password=s.password.get_secret_value(),
        )
        cfg = pyseekdb.HNSWConfiguration(
            dimension=self._dimension, distance="l2"
        )
        self.artifacts = self._client.get_or_create_collection(
            ARTIFACTS_COLLECTION, configuration=cfg, embedding_function=None
        )
        raw = self._client.get_raw_connection()
        with raw.cursor() as cur:
            cur.execute(_RELATIONS_DDL)

    def raw_connection(self):
        return self._client.get_raw_connection()

    @staticmethod
    def edge_id(src: str, kind: str, dst: str) -> str:
        digest = hashlib.sha1(f"{src}|{kind}|{dst}".encode()).hexdigest()
        return digest[:16]
