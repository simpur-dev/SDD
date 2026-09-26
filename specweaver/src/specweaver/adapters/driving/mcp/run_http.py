from __future__ import annotations

import asyncio

import uvicorn

from ....shared import di


async def _amain() -> None:
    async with di.run() as app:
        server_settings = app.settings.server
        http_app = app.mcp.http_app(path=server_settings.mcp_path)
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
