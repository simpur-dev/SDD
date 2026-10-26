from __future__ import annotations

import re
import socket
import urllib.request
import uuid

import pymysql
import pytest

from specweaver.adapters.driven.powercontext import (
    PowerContextClient,
    PowerContextMemory,
)
from specweaver.adapters.driven.seekdb import SeekdbClient
from specweaver.adapters.driven.seekdb.catalog import SeekdbCatalog
from specweaver.adapters.driven.seekdb.hybrid import SeekdbHybridSearch
from specweaver.shared.config import SeekDbSettings, Settings


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def pc_ready() -> bool:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({})
    )
    try:
        with opener.open(
            "http://127.0.0.1:8000/health/ready", timeout=3
        ) as resp:
            return resp.status == 200
    except OSError:
        return False


_TEST_DB_PATTERN = re.compile(r"sw_int_[0-9a-f]{8}\Z")


def drop_test_database(seek: SeekDbSettings) -> None:
    # DROP DATABASE is irreversible: the pattern guard keeps a misconfigured
    # database name from ever routing this at a real database.
    if not _TEST_DB_PATTERN.fullmatch(seek.database):
        return
    conn = pymysql.connect(
        host=seek.host,
        port=seek.port,
        user=seek.user,
        password=seek.password.get_secret_value(),
        connect_timeout=5,
        read_timeout=15,
        write_timeout=15,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{seek.database}`")
    finally:
        conn.close()


@pytest.fixture
def run_id() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
async def seekdb_adapters(run_id):
    if not port_open("127.0.0.1", 2881):
        pytest.skip("seekdb container is not available")
    settings = Settings()
    settings.seekdb.database = f"sw_int_{run_id}"
    client = SeekdbClient(settings.seekdb, dimension=8)
    client.initialize()
    try:
        yield SeekdbCatalog(client), SeekdbHybridSearch(client)
    finally:
        drop_test_database(settings.seekdb)


@pytest.fixture
async def seekdb_activity(run_id):
    if not port_open("127.0.0.1", 2881):
        pytest.skip("seekdb container is not available")
    from specweaver.adapters.driven.seekdb import SeekdbActivityLog

    settings = Settings()
    settings.seekdb.database = f"sw_int_{run_id}"
    client = SeekdbClient(settings.seekdb, dimension=8)
    client.initialize()
    try:
        yield SeekdbActivityLog(client), f"proj-{run_id}"
    finally:
        drop_test_database(settings.seekdb)


@pytest.fixture
async def pc_adapters(run_id):
    if not port_open("127.0.0.1", 8000) or not pc_ready():
        pytest.skip("powercontext container is not available")
    settings = Settings()
    client = PowerContextClient(settings.powercontext)
    project = f"int-{run_id}"
    scope_id = await PowerContextMemory(client).resolve_scope(project)
    try:
        yield client, project, scope_id, f"src-int-{run_id}"
    finally:
        await client.close()
