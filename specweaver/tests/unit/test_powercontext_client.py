from __future__ import annotations

import httpx
import pytest

from specweaver.adapters.driven.powercontext.client import PowerContextClient
from specweaver.shared.config import PowerContextSettings
from specweaver.shared.errors import BackendConnectionError, SWError
from specweaver.shared.telemetry import Telemetry


def _client_with_transport(handler) -> tuple[PowerContextClient, Telemetry]:
    telemetry = Telemetry()
    client = PowerContextClient(
        PowerContextSettings(), telemetry=telemetry
    )
    client._http = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return client, telemetry


async def test_request_counts_backend_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    client, telemetry = _client_with_transport(handler)
    with telemetry.span("op") as rec:
        await client.get("/v1/scopes")
    assert rec.backend_calls == 1


async def test_error_response_still_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client, telemetry = _client_with_transport(handler)
    with telemetry.span("op") as rec:
        with pytest.raises(SWError):
            await client.get("/v1/scopes")
    assert rec.backend_calls == 1


async def test_unreachable_not_counted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client, telemetry = _client_with_transport(handler)
    with telemetry.span("op") as rec:
        with pytest.raises(BackendConnectionError):
            await client.get("/v1/scopes")
    assert rec.backend_calls == 0
