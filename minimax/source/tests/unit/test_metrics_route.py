"""The Prometheus endpoint is added to the MCP HTTP app without breaking it."""
from __future__ import annotations

import httpx
from fastmcp import FastMCP

from specweaver.adapters.driving.mcp.run_http import with_metrics_route
from specweaver.shared.telemetry import Telemetry


def _client(http_app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http_app), base_url="http://sw"
    )


async def test_metrics_route_serves_prometheus_text() -> None:
    telemetry = Telemetry()
    with telemetry.span("get_context"):
        telemetry.record_backend_call()
        telemetry.record_metric("recall", 12)

    http_app = with_metrics_route(FastMCP("t").http_app(path="/mcp"), telemetry)
    async with _client(http_app) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'sw_spans_total{span="get_context"} 1\n' in response.text
    assert (
        'sw_engine_metric_sum{span="get_context",metric="recall"} 12.0'
        in response.text
    )


async def test_metrics_route_does_not_displace_the_mcp_route() -> None:
    mcp = FastMCP("t")
    http_app = with_metrics_route(mcp.http_app(path="/mcp"), Telemetry())
    paths = [getattr(route, "path", None) for route in http_app.routes]

    assert paths[0] == "/metrics"
    # the MCP endpoint itself stays registered, so the session manager
    # (its lifespan) is untouched by the insertion
    assert "/mcp" in paths
