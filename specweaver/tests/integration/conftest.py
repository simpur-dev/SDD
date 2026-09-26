from __future__ import annotations

import socket
import urllib.request
import uuid

import pytest

from specweaver.adapters.driven.powercontext import (
    PowerContextClient,
    PowerContextMemory,
)
from specweaver.adapters.driven.seekdb import SeekdbClient
from specweaver.adapters.driven.seekdb.catalog import SeekdbCatalog
from specweaver.adapters.driven.seekdb.hybrid import SeekdbHybridSearch
from specweaver.shared.config import Settings


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
    yield SeekdbCatalog(client), SeekdbHybridSearch(client)


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
