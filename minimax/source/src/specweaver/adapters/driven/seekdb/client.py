from __future__ import annotations

import asyncio
import hashlib

import pymysql
import pyseekdb

from ....shared.config import SeekDbSettings
from ....shared.errors import SWError

ARTIFACTS_COLLECTION = "sw_artifacts_v2"
RELATIONS_TABLE = "sw_relations_v2"

_RELATIONS_DDL = f"""
CREATE TABLE IF NOT EXISTS {RELATIONS_TABLE} (
  edge_id     VARCHAR(64) PRIMARY KEY,
  project_id  VARCHAR(64),
  src_id      VARCHAR(96),
  dst_id      VARCHAR(96),
  kind        VARCHAR(32),
  confidence  DOUBLE,
  evidence    VARCHAR(1024),
  UNIQUE KEY uq_edge (project_id, src_id, dst_id, kind)
) ORGANIZATION HEAP
"""

_CHANGESET_DDL = """
CREATE TABLE IF NOT EXISTS sw_change_set (
  change_id      VARCHAR(64) PRIMARY KEY,
  task_id        VARCHAR(64),
  project_id     VARCHAR(64),
  files_changed  TEXT,
  test_run_id    VARCHAR(64),
  base_checksum  VARCHAR(128),
  head_checksum  VARCHAR(128),
  ts             DATETIME(6)
) ORGANIZATION HEAP
"""

_TESTRUN_DDL = """
CREATE TABLE IF NOT EXISTS sw_test_run (
  test_run_id VARCHAR(64) PRIMARY KEY,
  task_id     VARCHAR(64),
  project_id  VARCHAR(64),
  command     VARCHAR(1024),
  total       INT,
  passed      INT,
  failed      INT,
  skipped     INT,
  commit_ref  VARCHAR(255),
  report_ref  VARCHAR(1024),
  ts          DATETIME(6)
) ORGANIZATION HEAP
"""

# evidence tables whose "newest first" read path depends on ts precision
_TS_TABLES = ("sw_change_set", "sw_test_run")

# A single backend operation must not outlive the caller's patience: when WSL
# reclaims the containers the socket can hang forever, and pyseekdb exposes no
# read timeout of its own, so the bound lives on our side of the boundary.
OP_TIMEOUT_SECONDS = 60


class SeekdbClient:
    """Owns the pyseekdb remote client; artifacts use a Collection, relations use a SQL table."""

    def __init__(
        self, settings: SeekDbSettings, dimension: int, telemetry=None
    ) -> None:
        self._settings = settings
        self._dimension = dimension
        self._client = None
        self._artifacts = None
        self._telemetry = telemetry

    def count_op(self) -> None:
        """Count one logical backend operation on the open telemetry span."""
        if self._telemetry is not None:
            self._telemetry.record_backend_call()

    @property
    def artifacts(self):
        self.count_op()
        return self._artifacts

    def initialize(self) -> None:
        s = self._settings
        bootstrap = pymysql.connect(
            host=s.host,
            port=s.port,
            user=s.user,
            password=s.password.get_secret_value(),
            autocommit=True,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
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
        self._artifacts = self._client.get_or_create_collection(
            ARTIFACTS_COLLECTION, configuration=cfg, embedding_function=None
        )
        raw = self._client.get_raw_connection()
        with raw.cursor() as cur:
            cur.execute(_RELATIONS_DDL)
            cur.execute(_CHANGESET_DDL)
            cur.execute(_TESTRUN_DDL)
            self._widen_legacy_ts(cur)

    @staticmethod
    def _widen_legacy_ts(cur) -> None:
        """Give an existing database back the ordering the read path promises.

        Databases created before the ts columns were microsecond-precise store
        whole seconds, so two evidence records written in the same second tie
        and `ORDER BY ts DESC` returns them in an arbitrary order - which makes
        "the last test run" in a Context Bundle a coin flip. IF NOT EXISTS
        never rewrites a live table, so the widening happens here instead.
        """
        names = ", ".join(f"'{table}'" for table in _TS_TABLES)
        cur.execute(
            "SELECT TABLE_NAME, DATETIME_PRECISION "
            "FROM information_schema.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ({names}) "
            "AND COLUMN_NAME = 'ts'"
        )
        for row in cur.fetchall() or []:
            # raw connections hand back dict rows (DictCursor)
            table = str(row["TABLE_NAME"])
            precision = int(row["DATETIME_PRECISION"])
            if table in _TS_TABLES and precision < 6:
                cur.execute(f"ALTER TABLE {table} MODIFY ts DATETIME(6)")

    def raw_connection(self):
        self.count_op()
        return self._client.get_raw_connection()

    async def run_op(self, fn, what: str):
        """Execute a blocking pyseekdb/pymysql call, translating backend
        failures into the domain error contract (docs/03 §7.1).

        The timeout bounds the await: pyseekdb owns its own connection and
        exposes no read timeout, so a wedged backend surfaces as SWError
        instead of hanging the CLI/MCP caller forever.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn), timeout=OP_TIMEOUT_SECONDS
            )
        except TimeoutError as exc:
            raise SWError(
                f"seekdb {what} timed out after {OP_TIMEOUT_SECONDS}s"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - SDK boundary
            raise SWError(f"seekdb {what} failed: {exc}") from exc

    @staticmethod
    def edge_id(project: str, src: str, kind: str, dst: str) -> str:
        digest = hashlib.sha1(
            f"{project}|{src}|{kind}|{dst}".encode()
        ).hexdigest()
        return digest[:16]
