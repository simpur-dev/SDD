"""Adapter edges that only fail in production: backend probes and MiniMax schema.

Both are contract surfaces - what a probe returns when a backend is down, and
the private request shape MiniMax expects - and neither is reachable through
the in-memory fakes the rest of the suite runs on.
"""
from __future__ import annotations

import json

import httpx
import pymysql
import pytest
from pydantic import SecretStr

from specweaver.adapters.driven.inference.minimax import MiniMaxEmbedding
from specweaver.adapters.driven.powercontext.health import check_powercontext
from specweaver.adapters.driven.seekdb import health as seekdb_health
from specweaver.adapters.driven.seekdb.health import check_seekdb
from specweaver.shared.config import (
    InferenceSettings,
    PowerContextSettings,
    SeekDbSettings,
)
from specweaver.shared.errors import BackendConnectionError, SWError

# --- PowerContext readiness ------------------------------------------------


async def test_powercontext_probe_returns_the_server_detail() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "ready"})

    out = await check_powercontext(
        PowerContextSettings(base_url="http://pc:8000"),
        transport=httpx.MockTransport(handler),
    )
    assert out["name"] == "powercontext" and out["ok"] is True
    assert out["detail"] == {"status": "ready"}
    assert seen == {"path": "/health/ready", "auth": None}


async def test_powercontext_probe_sends_the_configured_token() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"status": "ready"})

    settings = PowerContextSettings(
        base_url="http://pc:8000", token=SecretStr("tok")
    )
    await check_powercontext(settings, transport=httpx.MockTransport(handler))
    assert seen["auth"] == "Bearer tok"


@pytest.mark.parametrize("status", [401, 503])
async def test_probe_failure_becomes_backend_connection_error(
    status: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="nope")

    with pytest.raises(BackendConnectionError):
        await check_powercontext(
            PowerContextSettings(base_url="http://pc:8000"),
            transport=httpx.MockTransport(handler),
        )


async def test_probe_rejects_a_body_that_is_not_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>proxy page</html>")

    with pytest.raises(BackendConnectionError):
        await check_powercontext(
            PowerContextSettings(base_url="http://pc:8000"),
            transport=httpx.MockTransport(handler),
        )


# --- seekdb connectivity ---------------------------------------------------


class _FakeCursor:
    def __init__(self, error: Exception | None) -> None:
        self._error = error

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args) -> bool:
        return False

    def execute(self, sql: str) -> None:
        if self._error is not None:
            raise self._error

    def fetchone(self) -> tuple[str]:
        return ("5.7.25-test",)


class _FakeConnection:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._error)

    def close(self) -> None:
        self.closed = True


async def test_seekdb_probe_returns_version_and_closes(monkeypatch) -> None:
    conn = _FakeConnection()
    monkeypatch.setattr(seekdb_health.pymysql, "connect", lambda **kw: conn)
    assert await check_seekdb(SeekDbSettings()) == {
        "name": "seekdb",
        "ok": True,
        "version": "5.7.25-test",
    }
    assert conn.closed is True


async def test_seekdb_probe_translates_a_dead_server(monkeypatch) -> None:
    def refuse(**kwargs):
        raise pymysql.OperationalError(2003, "can't connect")

    monkeypatch.setattr(seekdb_health.pymysql, "connect", refuse)
    with pytest.raises(BackendConnectionError) as exc:
        await check_seekdb(SeekDbSettings())
    assert "unreachable" in exc.value.message


async def test_seekdb_probe_translates_a_failed_query(monkeypatch) -> None:
    boom = pymysql.err.ProgrammingError(1146, "no such table")
    monkeypatch.setattr(
        seekdb_health.pymysql,
        "connect",
        lambda **kwargs: _FakeConnection(boom),
    )
    with pytest.raises(BackendConnectionError):
        await check_seekdb(SeekDbSettings())


# --- MiniMax embo-01 (non-standard schema) ---------------------------------


def _minimax_settings() -> InferenceSettings:
    return InferenceSettings(
        provider="minimax",
        base_url="https://api.minimax.chat/v1",
        embed_model="embo-01",
        api_key=SecretStr("mk"),
    )


def _minimax(handler) -> MiniMaxEmbedding:
    return MiniMaxEmbedding(
        _minimax_settings(), transport=httpx.MockTransport(handler)
    )


async def test_minimax_sends_its_private_texts_and_type_body() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"vectors": [[0.5, 0.25], [0.1, 0.2]]})

    vectors = await _minimax(handler).embed(["a", "b"], kind="query")
    assert seen["url"].endswith("/embeddings")
    assert seen["auth"] == "Bearer mk"
    assert seen["body"] == {
        "model": "embo-01",
        "texts": ["a", "b"],
        "type": "query",
    }
    assert vectors == [[0.5, 0.25], [0.1, 0.2]]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, text="bad request"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"embeddings": []}),
    ],
)
async def test_minimax_turns_any_bad_answer_into_swerror(
    response: httpx.Response,
) -> None:
    with pytest.raises(SWError):
        await _minimax(lambda request: response).embed(["a"])


async def test_minimax_unreachable_is_backend_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(BackendConnectionError):
        await _minimax(handler).embed(["a"])
