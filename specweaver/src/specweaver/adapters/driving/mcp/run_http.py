from __future__ import annotations

import asyncio

import uvicorn
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from ....shared import di
from ....shared.telemetry import Telemetry


def with_metrics_route(http_app, telemetry: Telemetry):
    """Add a Prometheus /metrics endpoint to the MCP HTTP app in place.

    Mutating the existing Starlette routes keeps the FastMCP session
    manager's lifespan intact.
    """

    async def metrics(request) -> PlainTextResponse:
        return PlainTextResponse(
            telemetry.to_prometheus(),
            media_type="text/plain; version=0.0.4",
        )

    http_app.routes.insert(0, Route("/metrics", metrics))
    return http_app


async def _amain() -> None:
    async with di.run() as app:
        server_settings = app.settings.server
        http_app = with_metrics_route(
            app.mcp.http_app(path=server_settings.mcp_path),
            app.telemetry,
        )
        config = uvicorn.Config(
            http_app,
            host=server_settings.host,
            port=server_settings.port,
        )
        await uvicorn.Server(config).serve()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
